import threading
import subprocess
import shutil
from pathlib import Path
import socket
import traceback
import logging
import time

from pwnagotchi.plugins import Plugin
from pwnagotchi.ui.faces import LOOK_R, SAD, ANGRY, SMART

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
    __version__ = "1.0.4"
    __license__ = 'GPL3'
    __description__ = "Backup handshakes to OneDrive using rclone"

    def __init__(self):
        super().__init__()
        self.log = logging.getLogger("pwnagotchi.custom.onedrivebackup")
        self.log.setLevel(logging.INFO)
        self.log_prefix = "[OneDriveBackup] "
        self.backup_timer = None
        self._backup_lock = threading.Lock()
        self.ui = None
        self.ready = False
        self._pending_backup = None
        self._ui_face = None
        self._ui_status = None

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
            if hasattr(self, 'agent') and callable(self.agent.view):
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
        self.max_age = int(self.options.get("max_age", DEFAULT_MAX_AGE))
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
            if self.backup_timer and self.backup_timer.is_alive():
                self.backup_timer.cancel()
            self._backup_handshakes()
        except Exception as e:
            self._log_error(f"Backup failed: {e}")
        finally:
            try:
                self.backup_timer = threading.Timer(self.interval * 60, self._schedule_backup)
                self.backup_timer.start()
            except Exception as e:
                self._log_error(f"Failed to schedule next backup: {e}")

    def _backup_handshakes(self):
        lock_acquired = False
        try:
            if not self._backup_lock.acquire(blocking=True, timeout=300):
                self._log_error("Could not acquire backup lock after 5 minutes")
                return
            lock_acquired = True

            if self.backup_timer and not self.backup_timer.is_alive():
                self._log_warning("Found stale backup timer, resetting it")
                self.backup_timer.cancel()
                self.backup_timer = None

            if not self.ready:
                self._log_warning("Plugin not fully initialized - skipping backup")
                return

            self._log_info("Starting the backup process…")
            self.update_ui(LOOK_R, f"Backing up to {self.remote_name}")

            upload_success = True
            all_files = list(self.handshakes_dir.glob("*.*"))
            total_files = len(all_files)
            self._log_info(f"Found {total_files} files to backup")
            self.update_ui(LOOK_R, f"Backing up 0/{total_files} to {self.remote_name}")

            processed = 0
            successful_extensions = {}

            for target_file in all_files:
                processed += 1
                self.update_ui(LOOK_R, f"Backing up {processed}/{total_files} to {self.remote_name}")

                if self.test_mode:
                    ext = target_file.suffix.lower()
                    successful_extensions[ext] = successful_extensions.get(ext, 0) + 1
                    self._log_info(f"[Test mode] would upload {target_file.name}")
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
                except subprocess.TimeoutExpired:
                    self.update_ui(SAD, "Backup timed out")
                    self._log_error("Backup process timed out.")
                except FileNotFoundError as e:
                    self._log_error(f"rclone binary not found! Error: {e}")

            # final status
            if upload_success:
                self.update_ui(SMART, "Done!")
            else:
                count = sum(successful_extensions.values())
                self.update_ui(SAD, f"{count}/{total_files}")

        except subprocess.TimeoutExpired:
            self.update_ui(SAD, "Backup timed out")
            self._log_error("Backup process timed out.")
        except Exception as e:
            self.update_ui(ANGRY, "Error!")
            self._log_error(f"Unexpected error during backup: {e}")
            self._log_debug(traceback.format_exc())
        finally:
            if lock_acquired:
                self._log_info("Releasing the backup lock.")
                self._backup_lock.release()

    def on_handshake(self, agent, filename, access_point, client_station):
        """Called when a new handshake is captured"""
        if self._pending_backup and self._pending_backup.is_alive():
            self._pending_backup.cancel()

        self._log_info("New handshake captured, scheduling backup in 5 minutes")
        self._pending_backup = threading.Timer(300, self._backup_handshakes)
        self._pending_backup.start()

    def on_unload(self, ui):
        """Called when the plugin is unloaded"""
        self._log_info("Unloading plugin and cleaning up resources.")
        try:
            if self.backup_timer and self.backup_timer.is_alive():
                self.backup_timer.cancel()
            if self._pending_backup and self._pending_backup.is_alive():
                self._pending_backup.cancel()
        except Exception as e:
            self._log_error(f"Error during cleanup: {e}")
        finally:
            self.backup_timer = None
            self._pending_backup = None
            if self._backup_lock.locked():
                self._backup_lock.release()