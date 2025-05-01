# OneDriveBackup Plugin for Pwnagotchi

Automatically back up your Pwnagotchi handshakes and related files to Microsoft OneDrive using rclone.

## Features

- Backs up all files (pcap, json, pot, etc.) from your handshakes directory
- Supports both native OneDrive API and WebDAV connections
- Provides detailed logs with success rates by file extension
- Shows backup status on the Pwnagotchi UI
- Creates device-specific folders on OneDrive
- Smart backup timing: both scheduled and after new handshake captures
- Only uploads new or changed files to save bandwidth

## Installation

1. SSH into your Pwnagotchi
2. Install rclone:
   ```
   curl https://rclone.org/install.sh | sudo bash
   ```
3. Copy the plugin file to your plugins directory:
   ```
   wget -O /usr/local/share/pwnagotchi/installed-plugins/onedrivebackup.py https://raw.githubusercontent.com/AWWShuck/pwny-plugs/main/onedrivebackup.py
   ```
4. Configure rclone as described below
5. Update your `config.toml` to enable the plugin

## OneDrive Configuration

### Standard OneDrive Setup

1. On your PC, install rclone from [rclone.org/downloads](https://rclone.org/downloads/)
2. Configure OneDrive:
   ```
   rclone config
   # Select "n" for a new remote
   # Name: onedrive
   # Storage: Microsoft OneDrive
   # Follow the browser authentication flow
   ```
3. Copy your PC's rclone config file to your Pwnagotchi:
   ```
   # Windows: C:/Users/[YourUsername]/AppData/Roaming/rclone/rclone.conf
   # Mac/Linux: ~/.config/rclone/rclone.conf
   
   # On Pwnagotchi:
   sudo mkdir -p /root/.config/rclone
   sudo nano /root/.config/rclone/rclone.conf
   # Paste the [onedrive] section
   sudo chmod 600 /root/.config/rclone/rclone.conf
   ```

### WebDAV Setup (For Authentication Issues)

If you experience persistent authentication problems with the standard setup:

1. Find your OneDrive CID:
   - Sign in to OneDrive in your browser
   - Right-click any file and select "Copy link"
   - Open this link, and look for "cid=XXXXXXXX" in the URL

2. On your PC, create a WebDAV connection:
   ```
1. **Enable the Plugin**:  
   Add the following to your `config.toml` file:
   ```toml
   main.plugins.onedrivebackup.enabled = true
   main.plugins.onedrivebackup.handshakes_dir = "/home/pi/handshakes"
   main.plugins.onedrivebackup.interval = 60
   main.plugins.onedrivebackup.remote_name = "onedrive"
   main.plugins.onedrivebackup.remote_path = "handshakes"
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
   - Note you will need to use one of the methods listed here to get your oauth token https://rclone.org/remote_setup/

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
- Files are synced into a subfolder `<remote_path>/<hostname>` on OneDrive, so multiple devices don’t overwrite each other.
- On the Pwnagotchi’s LCD you’ll see:
  * “Backing up…” with the sync icon  
  * “Done!” with the check icon on success  
  * “Fail!” with the cross icon on failure  
  * “Error during backup” with the warning icon on exceptions

## Logs
Monitor the backup process:
```bash
tail -f /var/log/pwnagotchi.log
```

## Troubleshooting

### Authentication Issues

1. Create an app password instead of using your regular password
   - Go to https://account.microsoft.com/security
   - Create an app password specifically for rclone

2. Disable security defaults
   - Go to https://account.microsoft.com/security
   - Find and disable "Security defaults"

3. Try a different Microsoft account
   - Create a dedicated account for this purpose
   - Share your OneDrive folder with this account

4. Update rclone to the latest version
   ```
   curl https://rclone.org/install.sh | sudo bash
   ```

### Testing the Connection

Test your configuration directly:
```
sudo rclone --config /root/.config/rclone/rclone.conf lsd onedrive:
```

### Check for File Type Support

You can verify which file types are being backed up by checking the plugin logs, which now report success rates by file extension:

```
File extension summary:
  .pcap: 15/15 files uploaded successfully
  .json: 10/10 files uploaded successfully
  .pot: 5/5 files uploaded successfully
```

### Web UI Toggle Issues

If you encounter an error in logs about `on_unload()` taking 1 positional argument but 2 were given:
```
Update to the latest version of the plugin, which fixes an issue with enabling/disabling the plugin through the web UI.
```

## License

## Author
- **AWWShuck**
