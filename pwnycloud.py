import threading
import subprocess
import shutil
from pathlib import Path
import socket
import traceback
import logging
import time
import json

from pwnagotchi.plugins import Plugin
from pwnagotchi.ui.faces import LOOK_R, LOOK_L, SAD, ANGRY, SMART, UPLOAD, UPLOAD1, UPLOAD2

DEFAULT_HANDSHAKES_DIR = Path("/home/pi/handshakes")
DEFAULT_INTERVAL = 60
DEFAULT_REMOTE_NAME = "pwnycloud"
DEFAULT_REMOTE_PATH = "handshakes"
DEFAULT_MAX_AGE = 0

class PwnyCloud(Plugin):
    """
    PwnyCloud: Cloud backup plugin for Pwnagotchi

    Backs up handshakes and related files to any cloud provider supported by rclone.
    See README.md for detailed setup instructions.
    """
    __author__ = "AWWShuck"
    __version__ = "1.0.5"
    __license__ = 'GPL3'
    __description__ = "Backup handshakes to any cloud provider using rclone"

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger("pwnagotchi.custom.pwnycloud")
        self.log.setLevel(logging.INFO)
        self.log_prefix = "[PwnyCloud] "
        self.backup_timer = None
        self._backup_lock = threading.Lock()
        self.ui = None
        self.ready = False
        self._pending_backup = None
        self._ui_face = None
        self._ui_status = None
        self.last_backup_time = None
        if not hasattr(self, "options"):
            self.options = {}
        self._state_file = Path(self.options.get("state_file", DEFAULT_HANDSHAKES_DIR / ".pwnycloud_state.json"))
        self._uploaded_files = self._load_uploaded_files()

    def _log_info(self, msg):
        self.log.info(f"{self.log_prefix}{msg}")

    def _log_error(self, msg):
        self.log.error(f"{self.log_prefix}{msg}")

    def _log_warning(self, msg):
        self.log.warning(f"{self.log_prefix}{msg}")

    def _log_debug(self, msg):
        if self.log.level == logging.DEBUG:
            self.log.debug(f"{self.log_prefix}{msg}")

    def on_loaded(self):
        """Called when plugin is loaded"""
        log_level = self.options.get("log_level", "INFO").upper()
        self.log.setLevel(getattr(logging, log_level, logging.INFO))
        self._log_info("Plugin loaded")

        try:
            if hasattr(self, 'agent') and hasattr(self.agent, "view") and callable(self.agent.view):
                self.ui = self.agent.view()
                self._log_debug("UI reference acquired")
            else:
                self.ui = None
                self._log_warning("No UI available - will run without display updates")
        except Exception as e:
            self.ui = None
            self._log_warning(f"Could not get UI reference: {e}")

        self.handshakes_dir = Path(self.options.get("handshakes_dir", DEFAULT_HANDSHAKES_DIR))
        try:
            self.interval = max(int(self.options.get("interval", DEFAULT_INTERVAL)), 1)
            if self.interval > 1440:
                self._log_warning(f"Interval {self.interval} minutes is longer than 24 hours")
        except ValueError:
            self._log_error("Invalid interval value, using default")
            self.interval = DEFAULT_INTERVAL

        self.remote_name = self.options.get("remote_name", DEFAULT_REMOTE_NAME)
        self.remote_path = self.options.get("remote_path", DEFAULT_REMOTE_PATH)
        self.hostname = socket.gethostname()
        try:
            self.max_age = int(self.options.get("max_age", DEFAULT_MAX_AGE))
        except Exception:
            self.max_age = DEFAULT_MAX_AGE
        self.test_mode = self.options.get("test_mode", False)
        if self.test_mode:
            self._log_info("TEST MODE enabled: no files will be uploaded")

        if not self.handshakes_dir.exists():
            self._log_error(f"Handshake directory {self.handshakes_dir!r} missing; aborting backups.")
            return

        if not self._verify_rclone():
            return

        self.ready = True
        self._schedule_backup()

    def update_ui(self, face=None, status=None):
        """Queue a face and status for the next UI draw."""
        if face is not None:
            self._ui_face = face
        if status is not None:
            self._ui_status = status
        self._log_debug(f"UI state queued: face={face}, status={status}")

    def on_ui_update(self, ui):
        """Called every frame—draw queued face/status."""
        if self._ui_face is not None:
            ui.set('face', self._ui_face)
        if self._ui_status is not None:
            ui.set('status', self._ui_status)
        # Clear after drawing so it doesn't "stick"
        self._ui_face = None
        self._ui_status = None

    def _verify_rclone(self):
        if shutil.which("rclone") is None:
            self._log_error("rclone not found! Install it with: curl https://rclone.org/install.sh | sudo bash")
            return False

        check = subprocess.run(
            ["rclone", "--config", "/root/.config/rclone/rclone.conf", "listremotes"],
            capture_output=True, text=True
        )
        remotes = check.stdout.strip()
        expected = f"{self.remote_name}:"
        self._log_info(f"Available remotes: [{remotes}]")

        if expected not in remotes:
            self._log_error(f"Remote '{self.remote_name}' not found. Check rclone config.")
            return False

        try:
            test = subprocess.run(
                ["rclone", "--config", "/root/.config/rclone/rclone.conf",
                 "--auto-confirm", "lsd", expected],
                capture_output=True, text=True, timeout=30
            )
            if test.returncode != 0:
                self._log_error(f"Cannot access remote: {test.stderr.strip()}")
                return False
            self._log_info("Remote access verified successfully")
            return True
        except Exception as e:
            self._log_error(f"Error testing remote: {e}")
            self._log_debug(traceback.format_exc())
            return False

    def _schedule_backup(self):
        try:
            if self.backup_timer and hasattr(self.backup_timer, "is_alive") and self.backup_timer.is_alive():
                self.backup_timer.cancel()
            self._backup_handshakes()
        except Exception as e:
            self._log_error(f"Backup failed: {e}")
            self._log_debug(traceback.format_exc())
        finally:
            try:
                self.backup_timer = threading.Timer(self.interval * 60, self._schedule_backup)
                self.backup_timer.start()
            except Exception as e:
                self._log_error(f"Failed to schedule next backup: {e}")
                self._log_debug(traceback.format_exc())

    def _backup_handshakes(self):
        lock_acquired = False
        try:
            if not self._backup_lock.acquire(blocking=True, timeout=300):
                self._log_error("Could not acquire backup lock after 5 minutes")
                return
            lock_acquired = True

            if self.backup_timer and hasattr(self.backup_timer, "is_alive") and not self.backup_timer.is_alive():
                self._log_warning("Found stale backup timer, resetting it")
                self.backup_timer.cancel()
                self.backup_timer = None

            if not self.ready:
                self._log_warning("Plugin not fully initialized - skipping backup")
                return

            self._log_info(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Starting backup process…")
            self.update_ui(LOOK_R, f"Checking for new files…")

            start_time = time.time()

            # Use '*' to match all files, not just those with extensions
            all_files = list(self.handshakes_dir.glob("*"))
            files_to_upload = []
            for f in all_files:
                if not f.is_file():
                    continue
                mtime = int(f.stat().st_mtime)
                if f.name not in self._uploaded_files or self._uploaded_files[f.name] != mtime:
                    files_to_upload.append(f)

            total_files = len(files_to_upload)
            self._log_info(f"Found {total_files} new or changed files to backup")
            if total_files == 0:
                self.update_ui(SMART, "No new files")
                return

            upload_success = True
            successful_extensions = {}

            upload_faces = [UPLOAD, UPLOAD1, UPLOAD2]
            for idx, target_file in enumerate(files_to_upload, 1):
                face = upload_faces[(idx - 1) % len(upload_faces)]
                self.update_ui(face, f"Uploading ({idx}/{total_files})")
                time.sleep(1)  # Sleep 1 second between uploads
                if self.test_mode:
                    ext = target_file.suffix.lower()
                    successful_extensions[ext] = successful_extensions.get(ext, 0) + 1
                    self._log_info(f"[Test mode] would upload {target_file.name}")
                    # Do NOT update self._uploaded_files in test mode
                    continue

                file_target = f"{self.remote_name}:{self.remote_path}/{self.hostname}"
                file_cmd = [
                    "rclone", "--config", "/root/.config/rclone/rclone.conf",
                    "--auto-confirm", "--verbose", "--no-check-certificate",
                    "--retries", "3", "--low-level-retries", "5",
                    "--contimeout", "30s", "--timeout", "120s",
                    "--use-cookies", "--tpslimit", "10", "--progress",
                    "--ask-password=false", "--update", "--skip-links",
                    "--size-only", "copy", str(target_file), file_target
                ]

                try:
                    result = subprocess.run(file_cmd, capture_output=True, text=True, timeout=120)
                    if result.returncode != 0:
                        upload_success = False
                        self._log_error(f"Failed to upload {target_file.name}: {result.stderr.strip()}")
                    else:
                        ext = target_file.suffix.lower()
                        successful_extensions[ext] = successful_extensions.get(ext, 0) + 1
                        self._log_info(f"Uploaded {target_file.name} successfully")
                        self._uploaded_files[target_file.name] = int(target_file.stat().st_mtime)
                except subprocess.TimeoutExpired:
                    self.update_ui(SAD, "Backup timed out")
                    self._log_error("Backup process timed out.")
                    self._log_debug(traceback.format_exc())
                except FileNotFoundError as e:
                    self._log_error(f"rclone binary not found! Error: {e}")
                    self._log_debug(traceback.format_exc())
                except Exception as e:
                    upload_success = False
                    self._log_error(f"Unexpected error uploading {target_file.name}: {e}")
                    self._log_debug(traceback.format_exc())

            self._save_uploaded_files()

            duration = time.time() - start_time
            self._log_info(f"Backup completed in {duration:.2f} seconds")
            self.last_backup_time = time.strftime('%Y-%m-%d %H:%M:%S')
            self._log_info(f"Last backup at {self.last_backup_time}")

            # final status
            if upload_success:
                self.update_ui(SMART, "Done!")
            else:
                count = sum(successful_extensions.values())
                self.update_ui(SAD, f"{count}/{total_files}")

        except subprocess.TimeoutExpired:
            self.update_ui(SAD, "Backup timed out")
            self._log_error("Backup process timed out.")
            self._log_debug(traceback.format_exc())
        except Exception as e:
            self.update_ui(ANGRY, "Error!")
            self._log_error(f"Unexpected error during backup: {e}")
            self._log_debug(traceback.format_exc())
        finally:
            if lock_acquired:
                self._log_info("Releasing the backup lock.")
                self._backup_lock.release()

    def _load_uploaded_files(self):
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    return json.load(f)
        except Exception as e:
            self._log_warning(f"Could not load state file: {e}")
            self._log_debug(traceback.format_exc())
        return {}

    def _save_uploaded_files(self):
        try:
            # Ensure the state file directory exists
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w") as f:
                json.dump(self._uploaded_files, f)
        except Exception as e:
            self._log_warning(f"Could not save state file: {e}")
            self._log_debug(traceback.format_exc())

    def on_handshake(self, agent, filename, access_point, client_station):
        """Called when a new handshake is captured"""
        try:
            if self._pending_backup and hasattr(self._pending_backup, "is_alive") and self._pending_backup.is_alive():
                self._pending_backup.cancel()
        except Exception as e:
            self._log_warning(f"Error cancelling pending backup: {e}")
            self._log_debug(traceback.format_exc())

        self._log_info("New handshake captured, scheduling backup in 5 minutes")
        self._pending_backup = threading.Timer(300, self._backup_handshakes)
        self._pending_backup.start()

    def on_unload(self, ui=None):
        """Called when the plugin is unloaded"""
        self._log_info("Unloading plugin and cleaning up resources.")
        try:
            if self.backup_timer and hasattr(self.backup_timer, "is_alive") and self.backup_timer.is_alive():
                self.backup_timer.cancel()
            if self._pending_backup and hasattr(self._pending_backup, "is_alive") and self._pending_backup.is_alive():
                self._pending_backup.cancel()
        except Exception as e:
            self._log_error(f"Error during cleanup: {e}")
            self._log_debug(traceback.format_exc())
        finally:
            self.backup_timer = None
            self._pending_backup = None
            try:
                if self._backup_lock.locked():
                    self._backup_lock.release()
            except Exception as e:
                self._log_warning(f"Error releasing backup lock: {e}")
                self._log_debug(traceback.format_exc())