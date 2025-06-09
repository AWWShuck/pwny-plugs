import threading
import subprocess
import shutil
from pathlib import Path
import logging
import time
import json
import requests
import platform
from pwnagotchi.plugins import Plugin
from pwnagotchi.ui.components import LabeledValue
from pwnagotchi.ui.view import BLACK
from pwnagotchi.ui.view import fonts  # Ensure fonts is imported correctly
from pwnagotchi.ui.faces import LOOK_R, SMART, SAD, UPLOAD, UPLOAD1, UPLOAD2

DEFAULT_HANDSHAKES_DIR = Path("/home/pi/handshakes")
DEFAULT_INTERVAL = 60
DEFAULT_REMOTE_NAME = "pwnycloud"
DEFAULT_REMOTE_PATH = "handshakes"
DEFAULT_MAX_AGE = 0

def with_backup_lock(lock):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            if not lock.acquire(blocking=True, timeout=300):  # Wait up to 300 seconds
                self.log.warning(f"Could not acquire lock for {func.__name__}. Skipping execution.")
                return
            try:
                return func(self, *args, **kwargs)
            finally:
                lock.release()
        return wrapper
    return decorator

class PwnyCloud(Plugin):
    __author__ = "AWWShuck"
    __version__ = "1.0.8"
    __license__ = 'GPL3'
    __description__ = "Backup handshakes to any cloud provider using rclone"
    """
    Configuration options:
      - interval: Seconds between automatic backups (default: 60)
      - remote_name: Name of the rclone remote to use (default: pwnycloud)
      - remote_path: Path on the remote to store backups (default: handshakes)
      - handshakes_dir: Local directory with handshakes (default: /home/pi/handshakes)
      - max_age: Skip files older than this many days, 0=all (default: 0)
      - test_mode: Run without actually uploading (default: False)
      - rclone_options: Additional options for rclone (default: ["--progress", "--transfers=4"])
    
    Webhooks:
      - /plugins/pwnycloud/trigger: Trigger a backup
      - /plugins/pwnycloud/trigger?cmd=reset: Reset state and do full backup
    """

    def __init__(self):
        super().__init__()
        self.options = {}
        
        # Set up a file logger that will always be visible
        self.log = logging.getLogger("PwnyCloud")
        
        # Use INFO in production, DEBUG only during development
        self.log.setLevel(logging.INFO)  # Change from DEBUG to INFO
        
        # Console handler
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [%(name)s] [%(threadName)s]: %(message)s'))
        self.log.addHandler(handler)
        
        # Add a file handler that will log to a file we can check
        file_handler = logging.FileHandler('/tmp/pwnycloud_debug.log')
        file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] [%(threadName)s]: %(message)s'))
        self.log.addHandler(file_handler)
        
        self.backup_timer = None
        self._backup_lock = threading.Lock()
        self.ui = None
        self.ready = False
        self._pending_backup = None
        self._uploaded_files = {}
        self._state_file = None

        # Initialize fonts early to avoid timing issues
        fonts.setup(
            bold=10, bold_small=8, medium=10, huge=25, bold_big=25, small=9
        )

        self._validate_options()

    def _validate_options(self):
        defaults = {
            "interval": DEFAULT_INTERVAL,
            "remote_name": DEFAULT_REMOTE_NAME,
            "remote_path": DEFAULT_REMOTE_PATH,
            "max_age": DEFAULT_MAX_AGE,
            "test_mode": False,
            "rclone_options": ["--progress", "--transfers=4"],  # Example options
            "max_bw": "1M",  # Default 1MB/s
            "min_size": 0  # Default min size of 0 bytes
        }
        
        # First merge any user-provided options
        for key in defaults:
            if key not in self.options:
                self.options[key] = defaults[key]
        
        self._state_file = Path(self.options.get("state_file", DEFAULT_HANDSHAKES_DIR / ".pwnycloud_state.json"))
        self._uploaded_files = self._load_uploaded_files()

    def on_loaded(self):
        try:
            # More specific import with better error handling
            from pwnagotchi import __version__ as pwnagotchi_version
            self.log.info(f"Running on Pwnagotchi version: {pwnagotchi_version}")
            
            # Convert version string to comparable format if needed
            if hasattr(pwnagotchi_version, 'version') and pwnagotchi_version.version < "1.5.3":
                self.log.warning(f"This plugin is optimized for Pwnagotchi 1.5.3+, current: {pwnagotchi_version.version}")
        except ImportError:
            self.log.warning("Could not import Pwnagotchi version module")
        except AttributeError:
            self.log.warning("Pwnagotchi version module has unexpected structure")
        except Exception as e:
            self.log.warning(f"Could not determine Pwnagotchi version: {str(e)}")
        
        self.log.info("Plugin loaded")
        
        # Register webhook handlers if available
        if hasattr(self, 'register_webhook'):
            self.log.info("Registering webhooks...")
            self.register_webhook("/plugins/pwnycloud/trigger", self.on_webhook)
            self.register_webhook("/pwnycloud/trigger", self.on_webhook)
        
        self._initialize_ui()

    def _initialize_ui(self):
        if not hasattr(self, 'agent') or not self.agent:
            self.log.warning("Agent is not available. Delaying UI initialization.")
            return  # Wait for the on_ready event to initialize the UI

        self.ui = self.agent.view() if hasattr(self.agent, "view") and callable(self.agent.view) else None
        if not self.ui:
            self.log.warning("No UI available - running without display updates.")
            return

        self.ready = self._verify_rclone() and self._initialize_handshakes_dir()
        if self.ready:
            threading.Thread(
                target=self._backup_handshakes,
                daemon=True,
                name="PwnyCloud-InitialBackup"  # Explicitly set thread name
            ).start()

    def _initialize_handshakes_dir(self):
        self.handshakes_dir = Path(self.options.get("handshakes_dir", DEFAULT_HANDSHAKES_DIR))
        if not self.handshakes_dir.exists():
            self.log.error(f"Handshake directory {self.handshakes_dir!r} missing; aborting backups.")
            return False
        self.log.info(f"Using handshake directory: {self.handshakes_dir}")
        return True

    def on_ui_setup(self, ui):
        if fonts.Bold is None or fonts.Small is None:
            self.log.error("Fonts are not initialized. Ensure fonts.setup() is called.")
            return

        # Add a more descriptive backup status element with better spacing
        ui.add_element('backup_status', LabeledValue(
            color=BLACK,
            label=f"Bkp",  # Shortened to save space
            value=f"{self.options['remote_name']}",
            position=(0, 95),  # You can adjust this position if needed
            label_font=fonts.Bold,
            text_font=fonts.Small
        ))

    def on_ui_update(self, ui):
        if self.ready:
            if self._backup_lock.locked():
                status = "Sync: ..."
            else:
                last_sync = getattr(self, "_last_backup_time", None)
                if last_sync:
                    # Show time in HH:MM format
                    status = f"Sync: OK {time.strftime('%H:%M', time.localtime(last_sync))}"
                else:
                    status = "Sync: OK"
            ui.set('backup_status', status)

    def on_unload(self, ui):
        self.log.info("Unloading plugin and cleaning up resources.")
        self.ready = False  # Stop periodic backups
        self._cancel_timers()
        if self.ui:
            with ui._lock:
                ui.remove_element('backup_status')

    def _cancel_timers(self):
        self.ready = False  # This will signal threads to exit their loops
        try:
            if self._pending_backup and self._pending_backup.is_alive():
                # Wait a short time for thread to exit gracefully
                self._pending_backup.join(timeout=1)
        except Exception as e:
            self.log.error(f"Error during cleanup: {e}")
        finally:
            self._pending_backup = None
            if self._backup_lock.locked():
                self._backup_lock.release()

    def _verify_rclone(self, max_retries=3):
        """Verify rclone is installed and configured with retries"""
        for attempt in range(max_retries):
            self.log.info(f"Verifying rclone configuration (attempt {attempt+1}/{max_retries})")
            
            if shutil.which("rclone") is None:
                self.log.error("rclone not found! Install it with: curl https://rclone.org/install.sh | sudo bash")
                return False

            rclone_config_path = "/root/.config/rclone/rclone.conf"
            try:
                remotes = subprocess.run(
                    ["rclone", "--config", rclone_config_path, "listremotes"],
                    capture_output=True, text=True, check=True
                ).stdout.strip()
                if f"{self.options['remote_name']}:" not in remotes:
                    self.log.error(f"Remote '{self.options['remote_name']}' not found. Check rclone config.")
                    return False
                success = True
            except subprocess.CalledProcessError as e:
                self.log.error(f"Error verifying rclone: {e.stderr.strip()}")
                success = False

            if success:
                return True

            if attempt < max_retries - 1:
                self.log.info("Retrying in 5 seconds...")
                time.sleep(5)
        
        return False

    @with_backup_lock(lock=threading.Lock())
    def _backup_handshakes(self):
        self.log.info("Backup process triggered.")
        for handler in self.log.handlers:
            handler.flush()
        if not self.ready:
            self.log.warning("Plugin not fully initialized - skipping backup.")
            return
        try:
            has_internet = self._is_internet_available()
            self.log.info(f"Internet check result: {has_internet}")
            if not has_internet:
                self.update_ui(SAD, f"No internet - can't backup to {self.options['remote_name']}")
                self.log.warning("No internet connection - skipping backup.")
                return
            self.log.info("Starting backup process...")
            self.update_ui(LOOK_R, "Checking for new files…")
            try:
                files_to_upload = self._get_files_to_upload()
                self.log.info(f"Found {len(files_to_upload)} files to upload")
            except Exception as e:
                self.log.error(f"Exception in _get_files_to_upload: {e}", exc_info=True)
                return
            if not files_to_upload:
                self.update_ui(SMART, f"No new files for {self.options['remote_name']}")
                self.log.info("No new files to upload.")
                # Mark last sync time even if nothing to upload
                self._last_backup_time = int(time.time())
                return
            self.log.info(f"Uploading {len(files_to_upload)} files...")
            self._upload_files(files_to_upload)
            self.log.info("Backup process completed.")
            # Mark last sync time after successful backup
            self._last_backup_time = int(time.time())
        except Exception as e:
            self.log.error(f"Unexpected error in backup process: {e}", exc_info=True)
        finally:
            for handler in self.log.handlers:
                handler.flush()

    @with_backup_lock(lock=threading.Lock())
    def _upload_files(self, files_to_upload):
        upload_faces = [UPLOAD, UPLOAD1, UPLOAD2]
        for idx, target_file in enumerate(files_to_upload, 1):
            self.log.info(f"Uploading file {idx}/{len(files_to_upload)}: {target_file}")
            # Update both UI elements
            self.update_ui(
                upload_faces[(idx - 1) % len(upload_faces)], 
                f"Backing up {idx}/{len(files_to_upload)} to {self.options['remote_name']}"
            )
            if self.options.get("test_mode", False):
                self.log.info(f"[Test mode] would upload {target_file.name}")
                continue
            self._upload_file(target_file)
        
        # Update with completion message
        backup_count = len(self._uploaded_files)
        self.update_ui(SMART, f"Backed up {len(files_to_upload)} files to {self.options['remote_name']}")
        self.log.info("All files uploaded successfully.")
        self._save_uploaded_files()

    def _upload_file(self, target_file):
        rclone_options = self.options.get("rclone_options", [
            "--auto-confirm", "--verbose", "--no-check-certificate",
            "--retries", "3", "--low-level-retries", "5",
            "--contimeout", "30s", "--timeout", "120s",
            "--use-cookies", "--tpslimit", "10", "--progress",
            "--ask-password=false", "--update", "--skip-links",
            "--size-only"
        ])
        if self.options.get("max_bw"):
            rclone_options.append(f"--bwlimit={self.options['max_bw']}")
        file_target = f"{self.options['remote_name']}:{self.options['remote_path']}/{platform.node()}"
        file_cmd = [
            "rclone", "--config", "/root/.config/rclone/rclone.conf", "copy", str(target_file), file_target
        ] + rclone_options

        self.log.debug(f"Executing command: {' '.join(file_cmd)}")

        try:
            with subprocess.Popen(file_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as proc:
                stdout, stderr = proc.communicate()
                if proc.returncode != 0:
                    self.log.error(f"Failed to upload {target_file.name}: {stderr}")
                    return
            
            self.log.info(f"Uploaded {target_file.name} successfully")
            self._uploaded_files[target_file.name] = {
                "mtime": int(target_file.stat().st_mtime),
                "uploaded_at": int(time.time())
            }
            self._save_uploaded_files()
        except Exception as e:
            self.log.error(f"Error during upload of {target_file.name}: {str(e)}")

    def _save_uploaded_files(self):
        """Save the current state to disk"""
        try:
            with open(self._state_file, "w") as f:
                json.dump(self._uploaded_files, f)
            self.log.info(f"Saved state file with {len(self._uploaded_files)} entries")
        except Exception as e:
            self.log.error(f"Failed to save state file: {e}")

    def _load_uploaded_files(self):
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    data = json.load(f)
                    
                    # Migrate old format to new format
                    for key, value in list(data.items()):
                        if not isinstance(value, dict):
                            # Convert to new format
                            data[key] = {
                                "mtime": value,
                                "uploaded_at": int(time.time())
                            }
                            self.log.info(f"Migrated file record for {key} to new format")
                    
                    return data
        except json.JSONDecodeError as e:
            self.log.warning(f"State file is corrupted: {e}. Backing up and starting fresh.")
            backup_path = self._state_file.with_suffix(".bak")
            shutil.copy(self._state_file, backup_path)
            self._state_file.unlink()  # Remove the corrupted file
        except Exception as e:
            self.log.warning(f"Could not load state file: {e}")
        return {}

    def _is_internet_available(self):
        """Check if we have internet connectivity by trying to connect to known reliable sites"""
        self.log.info("Checking internet connectivity...")
        
        for url in ["https://www.google.com", "https://1.1.1.1", "https://cloudflare.com"]:
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    self.log.info(f"Internet verified via {url}")
                    return True
            except requests.exceptions.ConnectTimeout:
                self.log.debug(f"Connection to {url} timed out")
            except requests.exceptions.RequestException as e:
                self.log.debug(f"Request to {url} failed: {str(e)}")
        
        self.log.warning("No internet connection detected")
        return False

    def _get_files_to_upload(self):
        import os
        
        self.log.info("Starting to scan handshake directory")
        
        if not os.path.exists(str(self.handshakes_dir)):
            self.log.error(f"Handshake directory {self.handshakes_dir} does not exist")
            return []
        
        try:
            self.log.info("Scanning directory contents")
            file_names = os.listdir(str(self.handshakes_dir))
            self.log.info(f"Found {len(file_names)} items in directory")
            
            files_to_upload = []
            min_size = self.options.get("min_size", 0)  # Use get() with default value
            
            for name in file_names:
                self.log.debug(f"Processing {name}")
                full_path = os.path.join(str(self.handshakes_dir), name)
                
                # Skip directories and hidden files
                if not os.path.isfile(full_path) or name.startswith('.'):
                    continue
                
                # Skip files smaller than min_size (safely accessed)
                if os.path.getsize(full_path) < min_size:
                    self.log.debug(f"Skipping {name}: too small ({os.path.getsize(full_path)} bytes)")
                    continue
                    
                current_mtime = int(os.path.getmtime(full_path))
                
                # Handle both old format (int) and new format (dict) for stored timestamps
                stored_mtime = 0
                if name in self._uploaded_files:
                    if isinstance(self._uploaded_files[name], dict):
                        stored_mtime = self._uploaded_files[name].get("mtime", 0)
                    else:
                        # Old format where the value was just the mtime
                        stored_mtime = self._uploaded_files[name]
                
                if name not in self._uploaded_files or current_mtime > stored_mtime:
                    if name in self._uploaded_files:
                        self.log.info(f"File {name} has been modified since last backup (mtime: {current_mtime} vs {stored_mtime})")
                    else:
                        self.log.debug(f"Adding new file {name} to upload list")
                    files_to_upload.append(Path(full_path))
            
            self.log.info(f"Found {len(files_to_upload)} new or modified files to upload")
            return files_to_upload
        
        except Exception as e:
            self.log.error(f"Error listing directory: {e}", exc_info=True)
            return []

    def _schedule_backup(self):
        if self.backup_timer and self.backup_timer.is_alive():
            self.log.info("Existing backup timer will be replaced.")
            # No need to call cancel() on threads - they'll exit via the 'ready' flag

        self.log.info("Scheduling periodic backup...")
        # Run an immediate backup
        threading.Thread(
            target=self._backup_handshakes,
            daemon=True,
            name="PwnyCloud-InitialBackup"
        ).start()
        # Then start the periodic backup thread
        self.backup_timer = threading.Thread(
            target=self._periodic_backup,
            daemon=True,
            name="PwnyCloud-PeriodicBackup"
        )
        self.backup_timer.start()

    def _periodic_backup(self):
        try:
            while self.ready:
                self.log.info("Waiting for the next backup interval...")
                time.sleep(self.options.get("interval", DEFAULT_INTERVAL))
                self.log.info("Triggering periodic backup...")
                self._backup_handshakes()
        finally:
            for handler in self.log.handlers:
                handler.flush()

    def on_ready(self, agent):
        self.log.info("Agent is now available.")
        self.agent = agent  # Store the agent for later use
        self.ui = self.agent.view() if hasattr(self.agent, "view") and callable(self.agent.view) else None

        if not self.ui:
            self.log.warning("No UI available - running without display updates.")
            return

        self.ready = self._verify_rclone() and self._initialize_handshakes_dir()
        if self.ready:
            self._schedule_backup()  # Schedule periodic backups

    def trigger_backup(self):
        if not self.ready:
            self.log.warning("Plugin not fully initialized - cannot trigger backup.")
            return

        # Do a quick check if there are files to upload before starting a thread
        try:
            files_to_check = self._get_files_to_upload()
            if not files_to_check:
                self.log.info("No new files to upload - skipping backup")
                return
        except Exception:
            # If there's an error checking files, proceed with backup anyway
            pass
            
        self.log.info("Manually triggering backup...")
        threading.Thread(
            target=self._backup_handshakes,
            daemon=True,
            name="PwnyCloud-ManualBackup"
        ).start()

    def update_ui(self, face, text):
        """Update the UI with the given face and text if available."""
        if hasattr(self, 'agent') and self.agent and hasattr(self.agent, 'view'):
            view = self.agent.view()
            if view:
                view.set('face', face)
                view.set('status', text)
                self.log.debug(f"UI updated: face={face}, status={text}")
        else:
            self.log.debug(f"UI update skipped (no UI): face={face}, status={text}")

    def on_webhook(self, path, request):
        """Handles webhook requests to trigger backups from the web UI"""
        self.log.info(f"Received webhook with path: '{path}'")
        
        # Handle None path case
        if path is None:
            self.log.info("Path is None, treating as a trigger request")
            self.trigger_backup()
            return "Backup triggered successfully (from None path)!"

        # Extract command from request if present
        cmd = ""
        if hasattr(request, 'args') and 'cmd' in request.args:
            cmd = request.args['cmd']
            
        # Check for trigger paths
        if (path == "/plugins/pwnycloud/trigger" or 
            path == "/pwnycloud/trigger" or 
            "trigger" in str(path).lower() or
            str(path).endswith("/trigger") or
            not path):
            
            if cmd == "reset":
                self._uploaded_files = {}
                self._save_uploaded_files()
                self.log.info("Reset state file and triggering full backup")
            
            if cmd == "status":
                return {
                    "ready": self.ready,
                    "files_backed_up": len(self._uploaded_files),
                    "last_backup_time": getattr(self, "_last_backup_time", "Never"),
                    "remote_name": self.options["remote_name"],
                    "backup_interval": self.options["interval"]
                }
            
            self.trigger_backup()
            return "Backup triggered successfully!"
        
        return f"Unknown path: '{path}'. Try '/plugins/pwnycloud/trigger'"

    def on_handshake(self, agent, filename, access_point, client_station):
        """This is called when a new handshake is captured."""
        self.log.info(f"New handshake captured: {filename}")
        
        # Wait a moment for the file to be fully written
        time.sleep(2)
        
        # Extract just the filename without path
        handshake_filename = Path(filename).name
        
        # Check if this file is already in our uploaded files
        if handshake_filename in self._uploaded_files:
            self.log.info(f"Handshake {handshake_filename} already backed up, skipping trigger")
            return
        
        # Only trigger backup for new files
        self.log.info(f"New handshake needs backup: {handshake_filename}")
        self.trigger_backup()
        return