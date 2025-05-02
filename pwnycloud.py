import threading
import subprocess
import shutil
from pathlib import Path
import socket
import traceback
import logging
import time
import json
import requests
import platform

from pwnagotchi.plugins import Plugin
from pwnagotchi.ui.faces import LOOK_R, LOOK_L, SAD, ANGRY, SMART, UPLOAD, UPLOAD1, UPLOAD2

DEFAULT_HANDSHAKES_DIR = Path("/home/pi/handshakes")
DEFAULT_INTERVAL = 60
DEFAULT_REMOTE_NAME = "pwnycloud"
DEFAULT_REMOTE_PATH = "handshakes"
DEFAULT_MAX_AGE = 0

class PwnyCloud(Plugin):
    __author__ = "AWWShuck"
    __version__ = "1.0.6"
    __license__ = 'GPL3'
    __description__ = "Backup handshakes to any cloud provider using rclone"

    def __init__(self):
        super().__init__()
        if not hasattr(self, "options"):
            self.options = {}
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
        self._validate_options()
        self._state_file = Path(self.options.get("state_file", DEFAULT_HANDSHAKES_DIR / ".pwnycloud_state.json"))
        self._uploaded_files = self._load_uploaded_files()

    def _validate_options(self):
        defaults = {
            "interval": DEFAULT_INTERVAL,
            "remote_name": DEFAULT_REMOTE_NAME,
            "remote_path": DEFAULT_REMOTE_PATH,
            "max_age": DEFAULT_MAX_AGE,
            "test_mode": False,
        }
        self.options.update({key: defaults[key] for key in defaults if key not in self.options})

    def _log(self, level, msg):
        log_message = f"{self.log_prefix}{msg}"
        if level == "info":
            self.log.info(log_message)
        elif level == "error":
            self.log.error(log_message)
        elif level == "warning":
            self.log.warning(log_message)
        elif level == "debug" and self.log.level == logging.DEBUG:
            self.log.debug(log_message)

    def on_loaded(self):
        self._log("info", "Plugin loaded")
        try:
            if hasattr(self, 'agent') and hasattr(self.agent, "view") and callable(self.agent.view):
                self.ui = self.agent.view()
                self._log("debug", f"UI reference acquired: {self.ui is not None}")
            else:
                self.ui = None
                self._log("warning", "No UI available - will run without display updates")
        except Exception as e:
            self.ui = None
            self._log("warning", f"Could not get UI reference: {e}")

        if hasattr(self, 'agent') and self.agent.mode == "MANU":
            self._log("info", "Pwnagotchi is in manual mode.")

        self.handshakes_dir = Path(self.options.get("handshakes_dir", DEFAULT_HANDSHAKES_DIR))
        try:
            self.interval = max(int(self.options.get("interval", DEFAULT_INTERVAL)), 1)
            if self.interval > 1440:
                self._log("warning", f"Interval {self.interval} minutes is longer than 24 hours")
        except ValueError:
            self._log("error", "Invalid interval value, using default")
            self.interval = DEFAULT_INTERVAL

        self.remote_name = self.options.get("remote_name", DEFAULT_REMOTE_NAME)
        self.remote_path = self.options.get("remote_path", DEFAULT_REMOTE_PATH)
        self.hostname = platform.node()
        try:
            self.max_age = int(self.options.get("max_age", DEFAULT_MAX_AGE))
        except Exception:
            self.max_age = DEFAULT_MAX_AGE
        self.test_mode = self.options.get("test_mode", False)
        if self.test_mode:
            self._log("info", "TEST MODE enabled: no files will be uploaded")

        if not self.handshakes_dir.exists():
            self._log("error", f"Handshake directory {self.handshakes_dir!r} missing; aborting backups.")
            return

        if not self._verify_rclone():
            return

        self.ready = True
        self._validate_options()
        self._schedule_backup()

    def update_ui(self, face=None, status=None):
        if self.ui is None:
            self._log("debug", "UI is not available, skipping update.")  # Changed to debug
            return
        if face is not None:
            self._ui_face = face
        if status is not None:
            self._ui_status = status
        self._log("debug", f"UI state queued: face={face}, status={status}")

    def on_ui_update(self, ui):
        if self._ui_face is not None:
            ui.set('face', self._ui_face)
        if self._ui_status is not None:
            ui.set('status', self._ui_status)
        self._ui_face = None
        self._ui_status = None

    def _verify_rclone(self):
        self._log("info", "Using hardcoded rclone config path: /root/.config/rclone/rclone.conf")
        if shutil.which("rclone") is None:
            self._log("error", "rclone not found! Install it with: curl https://rclone.org/install.sh | sudo bash")
            return False

        rclone_config_path = "/root/.config/rclone/rclone.conf"
        check = subprocess.run(
            ["rclone", "--config", rclone_config_path, "listremotes"],
            capture_output=True, text=True
        )
        remotes = check.stdout.strip()
        expected = f"{self.remote_name}:"
        self._log("info", f"Available remotes: [{remotes}]")

        if expected not in remotes:
            self._log("error", f"Remote '{self.remote_name}' not found. Check rclone config.")
            return False

        try:
            test = subprocess.run(
                ["rclone", "--config", rclone_config_path, "--auto-confirm", "lsd", expected],
                capture_output=True, text=True, timeout=30
            )
            if test.returncode != 0:
                self._log("error", f"Cannot access remote: {test.stderr.strip()}")
                return False
            self._log("info", "Remote access verified successfully")
            return True
        except Exception as e:
            self._log("error", f"Error testing remote: {e}")
            self._log("debug", traceback.format_exc())
            return False

    def _schedule_backup(self):
        try:
            if self.backup_timer and self.backup_timer.is_alive():
                self.backup_timer.cancel()
            threading.Thread(target=self._backup_handshakes, daemon=True).start()
        except Exception as e:
            self._log("error", f"Failed to schedule backup: {e}")

    def _backup_handshakes(self):
        self._log("debug", f"UI state in _backup_handshakes: {self.ui is not None}")
        if not self._acquire_backup_lock():
            return

        try:
            if not self.ready:
                self._log("warning", "Plugin not fully initialized - skipping backup")
                return
            if not self._is_internet_available():
                self.update_ui(SAD, "No internet connection")
                return

            self._log("info", f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Starting backup process…")
            self.update_ui(LOOK_R, "Checking for new files…")

            files_to_upload = self._get_files_to_upload()
            if not files_to_upload:
                self.update_ui(SMART, "No new files")
                return

            self._upload_files(files_to_upload)
        finally:
            self._release_backup_lock()

    def _acquire_backup_lock(self):
        try:
            if not self._backup_lock.acquire(blocking=True, timeout=300):
                self._log("error", "Could not acquire backup lock after 5 minutes")
                return False
            return True
        except Exception as e:
            self._log("error", f"Error acquiring backup lock: {e}")
            return False

    def _release_backup_lock(self):
        try:
            if self._backup_lock.locked():
                self._backup_lock.release()
                self._log("info", "Backup lock released")
        except Exception as e:
            self._log("warning", f"Error releasing backup lock: {e}")

    def _get_files_to_upload(self):
        all_files = list(self.handshakes_dir.glob("*"))
        files_to_upload = [
            f for f in all_files if f.is_file() and (
                f.name not in self._uploaded_files or
                self._uploaded_files[f.name] != int(f.stat().st_mtime)
            )
        ]
        self._log("info", f"Found {len(files_to_upload)} new or changed files to backup")
        return files_to_upload

    def _upload_files(self, files_to_upload):
        upload_faces = [UPLOAD, UPLOAD1, UPLOAD2]
        upload_success = True
        successful_extensions = {}

        for idx, target_file in enumerate(files_to_upload, 1):
            face = upload_faces[(idx - 1) % len(upload_faces)]
            self.update_ui(face, f"Uploading ({idx}/{len(files_to_upload)})")
            time.sleep(1)
            if self.test_mode:
                self._log("info", f"[Test mode] would upload {target_file.name} (no state changes)")
                continue
            if not self._upload_file(target_file, successful_extensions):
                upload_success = False

        self._save_uploaded_files()
        self._log_upload_summary(upload_success, successful_extensions, len(files_to_upload))

    def _upload_file(self, target_file, successful_extensions):
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

        for attempt in range(3):  # Retry up to 3 times
            try:
                result = subprocess.run(file_cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0:
                    ext = target_file.suffix.lower()
                    successful_extensions[ext] = successful_extensions.get(ext, 0) + 1
                    self._log("info", f"Uploaded {target_file.name} successfully")
                    self._uploaded_files[target_file.name] = int(target_file.stat().st_mtime)
                    return True
                else:
                    self._log("error", f"Failed to upload {target_file.name} (attempt {attempt + 1}): {result.stderr.strip()}")
            except Exception as e:
                self._log("error", f"Error uploading {target_file.name} (attempt {attempt + 1}): {e}")
        return False

    def _log_upload_summary(self, upload_success, successful_extensions, total_files):
        if upload_success:
            self.update_ui(SMART, "Cloud Backup Completed!")
        else:
            count = sum(successful_extensions.values())
            self.update_ui(SAD, f"{count}/{total_files}")

    def _load_uploaded_files(self):
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    return json.load(f)
        except json.JSONDecodeError as e:
            self._log("warning", f"State file is corrupted: {e}. Resetting state.")
            self._state_file.unlink(missing_ok=True)  # Delete the corrupted file
        except Exception as e:
            self._log("warning", f"Could not load state file: {e}")
        return {}

    def _save_uploaded_files(self):
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._state_file, "w") as f:
                json.dump(self._uploaded_files, f)
        except Exception as e:
            self._log("warning", f"Could not save state file: {e}")
            self._log("debug", traceback.format_exc())

    def on_handshake(self, agent, filename, access_point, client_station):
        try:
            if self._pending_backup and hasattr(self._pending_backup, "is_alive") and self._pending_backup.is_alive():
                self._pending_backup.cancel()
        except Exception as e:
            self._log("warning", f"Error cancelling pending backup: {e}")
            self._log("debug", traceback.format_exc())

        self._log("info", "New handshake captured, scheduling backup in 5 minutes")
        self._pending_backup = threading.Timer(300, self._backup_handshakes)
        self._pending_backup.start()

    def on_unload(self, ui=None):
        self._log("info", "Unloading plugin and cleaning up resources.")
        try:
            if self.backup_timer and hasattr(self.backup_timer, "is_alive") and self.backup_timer.is_alive():
                self.backup_timer.cancel()
            if self._pending_backup and hasattr(self._pending_backup, "is_alive") and self._pending_backup.is_alive():
                self._pending_backup.cancel()
        except Exception as e:
            self._log("error", f"Error during cleanup: {e}")
            self._log("debug", traceback.format_exc())
        finally:
            self.backup_timer = None
            self._pending_backup = None
            try:
                if self._backup_lock.locked():
                    self._backup_lock.release()
            except Exception as e:
                self._log("warning", f"Error releasing backup lock: {e}")
                self._log("debug", traceback.format_exc())

    def _is_internet_available(self):
        urls = ["https://www.google.com", "https://www.cloudflare.com"]
        for url in urls:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    return True
            except requests.RequestException as e:
                self._log("warning", f"Internet check failed for {url}: {e}")
                self._log("debug", traceback.format_exc())
        return False