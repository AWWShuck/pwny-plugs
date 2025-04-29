# OneDrive Backup Plugin for Pwnagotchi
import threading
import subprocess
import shutil
from pathlib import Path

# add these imports:
from pwnagotchi.plugins import Plugin
from pwnagotchi import Status

# define defaults
DEFAULT_HANDSHAKES_DIR = Path("/home/pi/handshakes")
DEFAULT_INTERVAL = 60              # minutes
DEFAULT_REMOTE_NAME = "onedrive"
DEFAULT_REMOTE_PATH = "handshakes"

class OneDriveBackup(Plugin):
    __author__ = "AWWShuck"
    __version__ = "1.0.0"
    __license__ = 'GPL3'
    __description__ = "Backup handshakes to OneDrive using rclone"

    def __init__(self):
        super().__init__()
        self.backup_timer = None
        self._backup_lock = threading.Lock()

    def on_ready(self):
        # read & normalize config
        self.handshakes_dir = Path(self.options.get("handshakes_dir", DEFAULT_HANDSHAKES_DIR))
        self.interval = max(int(self.options.get("interval", DEFAULT_INTERVAL)), 1)
        self.remote_name = self.options.get("remote_name", DEFAULT_REMOTE_NAME)
        self.remote_path = self.options.get("remote_path", DEFAULT_REMOTE_PATH)

        if not self.handshakes_dir.exists():
            self.log.error(f"Handshake directory {self.handshakes_dir!r} missing; aborting backups.")
            return

        if shutil.which("rclone") is None:
            self.log.error("rclone not found; install & configure it manually before enabling this plugin.")
            return

        self._schedule_backup()

    def _schedule_backup(self):
        # run immediately, then every interval
        self._backup_handshakes()
        self.backup_timer = threading.Timer(self.interval * 60, self._schedule_backup)
        self.backup_timer.start()

    def _backup_handshakes(self):
        if not self._backup_lock.acquire(blocking=False):
            self.log.warning("Previous backup still in progress; skipping this cycle.")
            return

        try:
            self.log.info(f"Backing up from {self.handshakes_dir} → {self.remote_name}:{self.remote_path}")
            for f in self.handshakes_dir.rglob("*"):
                if f.is_file():
                    self.log.debug(f" - {f}")

            cmd = [
                "rclone", "sync",
                str(self.handshakes_dir),
                f"{self.remote_name}:{self.remote_path}"
            ]
            # fix logging call here:
            self.log.debug(f"Running: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                self.log.info("Backup completed successfully.")
                self.update_status(Status("Handshakes backed up!"))
            else:
                self.log.error(f"Backup failed ({result.returncode}): {result.stderr.strip()}")

        except Exception as e:
            self.log.error(f"Unexpected error during backup: {e}")
        finally:
            self._backup_lock.release()

    def on_unload(self):
        if self.backup_timer:
            self.backup_timer.cancel()
            self.backup_timer = None
        self.log.info("OneDrive plugin unloaded.")