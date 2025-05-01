import threading
import subprocess
import shutil
from pathlib import Path
import socket
import traceback
import logging
import time

from pwnagotchi.plugins import Plugin
from pwnagotchi.ui.faces import LOOK_R, HAPPY, SAD, ANGRY

DEFAULT_HANDSHAKES_DIR = Path("/home/pi/handshakes")
DEFAULT_INTERVAL = 60
DEFAULT_REMOTE_NAME = "onedrive"
DEFAULT_REMOTE_PATH = "handshakes"
DEFAULT_MAX_AGE = 0

class OneDriveBackup(Plugin):
    """
    OneDrive backup plugin for Pwnagotchi
    
    Backs up handshakes and related files to Microsoft OneDrive using rclone
    See README.md for detailed setup instructions
    """
    __author__ = "AWWShuck"
    __version__ = "1.0.1"
    __license__ = 'GPL3'
    __description__ = "Backup handshakes to OneDrive using rclone"

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger("pwnagotchi.custom.onedrivebackup")
        self.log.setLevel(logging.INFO)
        self.log_prefix = "[OneDriveBackup] "  # Adding a prefix for easy grep
        self.backup_timer = None
        self._backup_lock = threading.Lock()
        self.ui = None
        self.ready = False
        
    # Helper methods for logging with consistent prefix
    def _log_info(self, msg):
        self.log.info(f"{self.log_prefix}{msg}")
        
    def _log_error(self, msg):
        self.log.error(f"{self.log_prefix}{msg}")
        
    def _log_warning(self, msg):
        self.log.warning(f"{self.log_prefix}{msg}")
        
    def _log_debug(self, msg):
        self.log.debug(f"{self.log_prefix}{msg}")

    def on_loaded(self):
        """Called when plugin is loaded"""
        self._log_info("Plugin loaded")
        
        try:
            if hasattr(self, 'agent'):
                self.ui = self.agent.view
                self._log_debug("UI reference acquired")
            else:
                self.ui = None
                self._log_info("No UI available - will run without display updates")
        except Exception as e:
            self.ui = None
            self._log_warning(f"Could not get UI reference: {e}")

        def update_ui(face=None, status=None):
            if self.ui:
                try:
                    if face:
                        self.ui.show_face(face)
                    if status:
                        self.ui.set_status(status)
                except Exception as e:
                    self._log_debug(f"UI update failed: {e}")

        self.update_ui = update_ui

        self.handshakes_dir = Path(self.options.get("handshakes_dir", DEFAULT_HANDSHAKES_DIR))
        self.interval = max(int(self.options.get("interval", DEFAULT_INTERVAL)), 1)
        self.remote_name = self.options.get("remote_name", DEFAULT_REMOTE_NAME)
        self.remote_path = self.options.get("remote_path", DEFAULT_REMOTE_PATH)
        self.hostname = socket.gethostname()
        self.max_age = int(self.options.get("max_age", DEFAULT_MAX_AGE))
        self.test_mode = self.options.get("test_mode", False)

        if not self.handshakes_dir.exists():
            self._log_error(f"Handshake directory {self.handshakes_dir!r} missing; aborting backups.")
            return

        if not self._verify_rclone():
            return

        self.ready = True
        self._schedule_backup()

    def _verify_rclone(self):
        """Check rclone prerequisites and remote configuration"""
        if shutil.which("rclone") is None:
            self._log_error("rclone not found! Install it with: curl https://rclone.org/install.sh | sudo bash")
            return False

        check_remote = subprocess.run(
            ["rclone", "--config", "/root/.config/rclone/rclone.conf", "listremotes"],
            capture_output=True,
            text=True
        )
        available = check_remote.stdout.strip()
        expected_remote = f"{self.remote_name}:"
        
        self._log_info(f"Looking for remote '{expected_remote}' in available: [{available}]")
        
        if not available:
            self._log_error("No rclone remotes found. See README.md for setup instructions.")
            return False
            
        if expected_remote not in available:
            self._log_error(f"Remote '{expected_remote}' not found in available remotes: [{available}]")
            return False
        
        test_cmd = [
            "rclone",
            "--config", "/root/.config/rclone/rclone.conf",
            "--auto-confirm",
            "lsd",
            f"{self.remote_name}:"
        ]
        self._log_info(f"Testing remote access with: {' '.join(test_cmd)}")
        
        try:
            result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
            
            if "unauthenticated" in result.stderr.lower():
                self._log_error("OneDrive authentication failed. See README.md for troubleshooting.")
                return False
                
            if "permission denied" in result.stderr.lower():
                self._log_error("Rclone config permission denied. Fix with: sudo chmod 600 /root/.config/rclone/rclone.conf")
                return False
                
            if result.returncode != 0:
                self._log_error(f"Could not access remote. Error: {result.stderr.strip()}")
                return False
                
            self._log_info("Remote access verified successfully")
            return True
            
        except Exception as e:
            self._log_error(f"Error testing remote access: {e}")
            self._log_debug(traceback.format_exc())
            return False

    def _schedule_backup(self):
        try:
            self._backup_handshakes()
            self.backup_timer = threading.Timer(self.interval * 60, self._schedule_backup)
            self.backup_timer.start()
        except Exception as e:
            self._log_error(f"Backup failed, not scheduling next run: {e}")
            if self.backup_timer:
                self.backup_timer.cancel()
                self.backup_timer = None

    def _backup_handshakes(self):
        if self.backup_timer and not self.backup_timer.is_alive():
            self._log_warning("Found stale backup timer, resetting it")
            self.backup_timer.cancel()
            self.backup_timer = None

        if not self.ready:
            self._log_warning("Plugin not fully initialized - skipping backup")
            return

        if not self._backup_lock.acquire(blocking=True, timeout=300):
            self._log_error("Could not acquire backup lock after 5 minutes")
            return

        self._log_info("Starting the backup process...")

        if self.test_mode:
            self._log_info("Running in test mode - will simulate backup but not transfer files")

        try:
            self._log_info(f"Configuration: handshakes_dir={self.handshakes_dir}, remote_name={self.remote_name}, remote_path={self.remote_path}, hostname={self.hostname}")
            self.update_ui(LOOK_R, "Backing up…")
            self._log_info(f"Backing up from {self.handshakes_dir} → {self.remote_name}:{self.remote_path}")

            upload_success = True
            
            all_files = list(self.handshakes_dir.glob("*.*"))
            total_files = len(all_files)
            self._log_info(f"Found {total_files} files to backup")
            
            if total_files == 0:
                self._log_info("No files found to backup, skipping.")
                self.update_ui(LOOK_R, "No files!")
                return
            
            current_time = time.time()
            filtered_files = []
            for f in all_files:
                if self.max_age > 0:
                    file_age_days = (current_time - f.stat().st_mtime) / (24 * 3600)
                    if file_age_days > self.max_age:
                        self._log_debug(f"Skipping {f.name} - too old ({file_age_days:.1f} days)")
                        continue
                filtered_files.append(f)

            all_files = filtered_files
            total_files = len(all_files)
            
            processed = 0
            extension_counts = {}
            successful_extensions = {}
            
            for target_file in all_files:
                extension = target_file.suffix.lower()
                if extension in extension_counts:
                    extension_counts[extension] += 1
                else:
                    extension_counts[extension] = 1
                    successful_extensions[extension] = 0
                
                file_target = f"{self.remote_name}:{self.remote_path}/{self.hostname}"
                file_cmd = [
                    "rclone",
                    "--config", "/root/.config/rclone/rclone.conf",
                    "--auto-confirm",
                    "--verbose",
                    "--no-check-certificate",
                    "--retries", "3",
                    "--low-level-retries", "5",
                    "--contimeout", "30s",
                    "--timeout", "120s",
                    "--use-cookies",
                    "--tpslimit", "10",
                    "--progress",
                    "--ask-password=false",
                    "--update",
                    "--skip-links",  # Skip symlinks which can cause issues
                    "--size-only",   # Compare file sizes instead of times (more reliable)
                    "copy",
                    str(target_file),
                    file_target
                ]
                
                processed += 1
                self._log_info(f"Uploading file {processed}/{total_files}: {target_file.name}")
                
                if not self.test_mode:
                    file_result = subprocess.run(file_cmd, capture_output=True, text=True, timeout=120)
                    
                    if "skipped" in file_result.stdout.lower():
                        self._log_info(f"Skipped unchanged file: {target_file.name}")
                        successful_extensions[extension] += 1
                        continue

                    if file_result.returncode != 0:
                        self._log_error(f"Failed to upload {target_file.name}: {file_result.stderr.strip()}")
                        
                        if "401 unauthorized" in file_result.stderr.lower():
                            self._log_error("401 Unauthorized error detected. See README.md for troubleshooting.")
                        elif "429 too many requests" in file_result.stderr.lower():
                            self._log_error("Rate limiting detected. Backing off...")
                        elif "404 not found" in file_result.stderr.lower():
                            self._log_error(f"Remote path {file_target} not found. Verify it exists.")
                        elif "connection reset by peer" in file_result.stderr.lower():
                            self._log_error("Network connection issues detected.")
                            
                        upload_success = False
                    else:
                        self._log_info(f"Successfully uploaded: {target_file.name}")
                        successful_extensions[extension] += 1
                else:
                    self._log_info(f"Simulated upload for: {target_file.name}")
                    successful_extensions[extension] += 1
            
            self._log_info("File extension summary:")
            for ext, count in extension_counts.items():
                success_count = successful_extensions.get(ext, 0)
                self._log_info(f"  {ext}: {success_count}/{count} files uploaded successfully")
            
            if upload_success:
                self.update_ui(HAPPY, "Done!")
                self._log_info("All files backed up successfully.")
            else:
                success_count = sum(successful_extensions.values())
                self.update_ui(SAD, f"{success_count}/{total_files}")
                self._log_error(f"{success_count} of {total_files} files backed up successfully.")

        except subprocess.TimeoutExpired:
            self.update_ui(SAD, "Backup timed out")
            self._log_error("Backup process timed out.")

        except Exception as e:
            self.update_ui(ANGRY, "Error!")
            self._log_error(f"Unexpected error during backup: {e}")
            self._log_debug(traceback.format_exc())

        finally:
            self._log_info("Releasing the backup lock.")
            self._backup_lock.release()

    def on_handshake(self, agent, filename, access_point, client_station):
        """Called when a new handshake is captured"""
        if hasattr(self, '_pending_backup') and self._pending_backup:
            self._pending_backup.cancel()
        
        self._log_info(f"New handshake captured, scheduling backup in 5 minutes")
        self._pending_backup = threading.Timer(300, self._backup_handshakes)
        self._pending_backup.start()

    def on_unload(self):
        if self.backup_timer:
            self.backup_timer.cancel()
            self.backup_timer = None
        
        if hasattr(self, '_pending_backup') and self._pending_backup:
            self._pending_backup.cancel()
            self._pending_backup = None
        
        self._log_info("OneDrive plugin unloaded.")