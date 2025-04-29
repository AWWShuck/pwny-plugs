# pwny-plugs
My own custom Pwnagotchi Plugins

# OneDriveBackup Plugin for Pwnagotchi

The `OneDriveBackup` plugin automatically backs up handshakes from your Pwnagotchi to Microsoft OneDrive using `rclone`.

## Features
- Periodically backs up handshakes to OneDrive.
- Configurable backup interval, handshake directory, remote name and path.

## Requirements
- A Pwnagotchi device running on a Raspberry Pi.
- `rclone` installed and configured for OneDrive.

## Installation
1. **Enable the Plugin**:  
   Add the following to your `config.toml` file:
   ```toml
   # match plugin file onedrivebackup.py (no underscore)
   main.plugins.onedrivebackup.enabled         = true
   main.plugins.onedrivebackup.handshakes_dir  = '/home/pi/handshakes'
   main.plugins.onedrivebackup.interval        = 60
   main.plugins.onedrivebackup.remote_name     = 'onedrive'
   main.plugins.onedrivebackup.remote_path     = 'handshakes'
   ```

2. **Install `rclone`**:  
   You must install `rclone` manually if it is not already installed:
   ```bash
   sudo apt update
   sudo apt install -y rclone
   ```

3. **Configure `rclone` for OneDrive**:  
   Run:
   ```bash
   rclone config
   ```
   - Select `n` to create a new remote.  
   - Enter the name you set in `remote_name` (e.g., `onedrive`).  
   - Select `OneDrive` as the storage type.  
   - Follow the prompts to authenticate with your Microsoft account.

4. **Verify the Configuration**:  
   ```bash
   rclone lsd <remote_name>:
   ```
   e.g.
   ```bash
   rclone lsd onedrive:
   ```

## Usage
Once the plugin is enabled and configured:
- Backups run immediately on startup and then at each interval.
- Logs indicate the status of each backup.

## Logs
Monitor the backup process:
```bash
tail -f /var/log/pwnagotchi.log
```

## Troubleshooting
- **`rclone` Not Installed**:  
  Ensure your Pi has internet and install `rclone` manually:
  ```bash
  sudo apt update
  sudo apt install -y rclone
  ```
- **Authentication Issues**:  
  Re-run:
  ```bash
  rclone config
  ```
- **Backup Fails**:  
  Check plugin logs:
  ```bash
  tail -f /var/log/pwnagotchi.log
  ```

## Configuration Options
- `handshakes_dir`  : Directory containing handshake files. Default: `/home/pi/handshakes`
- `interval`        : Backup interval in minutes. Default: `60`
- `remote_name`     : Name of the `rclone` remote. Default: `onedrive`
- `remote_path`     : Path inside the remote. Default: `handshakes`

## License
This plugin is licensed under the GPL3 license.

## Author
- **AWWShuck**