# Changelog

## [1.0.8] - 2025-06-09
### Changed
- Updated UI sync status to a minimalist hybrid: now displays `Sync: OK` with the last successful sync time (HH:MM) after OK.
- Removed file count from on-display sync status for a cleaner look.
- Improved clarity of sync state: shows `Sync: ...` when syncing, `Sync: OK [time]` when idle, and `Sync: OK` if never synced.

---

## [1.0.7] - 2025-05-02
### Added
- Webhook support for triggering backups remotely via web browser
- Automatic backup when new handshakes are captured
- Compact UI with status display showing upload count with arrow indicator
- 'Reset' command to clear upload history and force full backup
- Status API to query current backup state and statistics

### Fixed
- Potential race condition in backup process
- Thread cancellation method for cleaner shutdown
- Path handling in webhook URLs
- State file handling when corrupt or missing

### Changed
- Reduced log verbosity for production environments
- Better request parameter handling in webhooks
- Added file-based logging for easier troubleshooting
- Enhanced error handling for network connectivity issues
- Improved thread management to prevent resource leaks

---

## [1.0.6] - 2025-05-01
### Added
- Initial release of the PwnyCloud plugin.
- Backup handshakes to any cloud provider using rclone.
- Automatic scheduling of backups with customizable intervals.
- Test mode for simulating uploads without making changes.
- UI updates for backup status and progress.

### Fixed
- Improved error handling for rclone configuration and remote access.
- Resolved issues with corrupted state files during backup.

### Changed
- Enhanced logging for better debugging and monitoring.
- Adjusted UI update logic to handle missing or unavailable UI references.

### Removed
- Deprecated methods for handling backups.

---

## [1.0.5] - 2025-05-01
### Added
- Support for verifying internet connectivity before backups.
- Retry mechanism for failed file uploads.

### Fixed
- Addressed issues with backup lock acquisition timing out.
- Improved error messages for failed uploads.

### Changed
- Optimized file upload logic to reduce redundant operations.

---

## [1.0.4] - 2025-05-01
### Added
- Support for handling large numbers of files during backup.
- Logging of successful file extensions for better analytics.

### Fixed
- Resolved issues with UI updates not reflecting backup progress.
- Fixed a bug where backups would fail if the remote path was missing.

### Changed
- Increased timeout for rclone operations to handle slower networks.

---

## [1.0.3] - 2025-05-01
### Added
- Automatic creation of missing directories for state files.
- Detailed logging for corrupted state file recovery.

### Fixed
- Fixed a bug where backups would not start if the handshake directory was empty.

### Changed
- Improved state file handling to prevent data loss during crashes.

---

## [1.0.2] - 2025-04-30
### Added
- Support for manual mode detection in Pwnagotchi.
- Additional logging for debugging UI-related issues.

### Fixed
- Resolved issues with incorrect interval values causing crashes.

### Changed
- Adjusted default interval to 60 minutes for better usability.

---

## [1.0.1] - 2025-04-29
### Added
- Initial implementation of the `_verify_rclone` method for remote validation.
- Basic error handling for missing rclone installations.

### Fixed
- Fixed a bug where the plugin would fail to load without a valid configuration.

### Changed
- Updated default paths for handshakes and state files.

---

## [1.0.0] - 2025-04-2029
### Added
- OneDrive Backup Plugin for Pwnagotchi to back up handshake files to OneDrive using `rclone`.
- Automatic scheduling of backups at configurable intervals (default: 60 minutes).
- Support for custom handshake directories and remote paths.
- Integration with `rclone` for syncing files to OneDrive.
- Logging of backup progress and errors.
- Thread-safe backup process using a lock to prevent overlapping backups.
- Graceful handling of missing directories or `rclone` installation.
- Cleanup of resources when the plugin is unloaded.

