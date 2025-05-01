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
   rclone config
   # Select "n" for a new remote
   # Name: onedrive_webdav
   # Storage: WebDAV
   # URL: https://d.docs.live.net/YOUR_CID_HERE
   # Select "Other" for vendor
   # User: your-microsoft@email.com
   # Password: yourpassword (or app password if 2FA enabled)
   ```

3. Copy this config to your Pwnagotchi as described above

4. Update your Pwnagotchi config to use this remote name:
   ```
   main.plugins.onedrivebackup.remote_name = "onedrive_webdav"
   ```

## Other Cloud Providers

While this plugin was developed and tested with Microsoft OneDrive, the underlying rclone tool supports many different cloud storage providers including:

- Google Drive
- Dropbox
- Amazon S3
- Box
- pCloud
- And many others

This plugin should theoretically work with any of these providers by changing the remote configuration, though these alternative providers have not been extensively tested. If OneDrive isn't working for you, setting up another provider like Google Drive might be a good alternative.

## Configuration Options

Add these to your `/etc/pwnagotchi/config.toml`:

### Required Settings

```
main.plugins.onedrivebackup.enabled = true  # Enable the plugin
main.plugins.onedrivebackup.remote_name = "onedrive"  # Must match your rclone remote name
```

### Optional Settings (with defaults)

```
main.plugins.onedrivebackup.handshakes_dir = "/home/pi/handshakes"  # Directory to back up
main.plugins.onedrivebackup.remote_path = "handshakes"  # Path on your cloud storage
main.plugins.onedrivebackup.interval = 60  # Minutes between scheduled backups
main.plugins.onedrivebackup.max_age = 0  # Maximum file age in days (0 = no limit)
main.plugins.onedrivebackup.test_mode = false  # Simulate backups without transfers
```

## Backup Behavior

This plugin performs backups in two ways:
1. **Scheduled backups**: Runs every `interval` minutes (default: 60)
2. **Event-triggered backups**: Runs 5 minutes after a new handshake is captured

This hybrid approach ensures your handshakes are backed up regularly, but also soon after capturing them, without wasting battery on immediate uploads.

## Advanced: rclone Options

This plugin uses the following rclone options for optimal reliability with OneDrive:

```
rclone \
  --config /root/.config/rclone/rclone.conf \
  --auto-confirm \
  --verbose \
  --no-check-certificate \
  --retries 3 \
  --low-level-retries 5 \
  --contimeout 30s \
  --timeout 120s \
  --use-cookies \
  --tpslimit 10 \
  --progress \
  --ask-password=false \
  --update \
  --skip-links \
  --size-only \
  copy \
  [file] \
  [destination]
```

These options are optimized for:

- **Authentication & Security**
  - `--auto-confirm`: Doesn't prompt for confirmation during operations
  - `--no-check-certificate`: Skips TLS certificate verification (useful on Pwnagotchi)
  - `--use-cookies`: Maintains authentication sessions between operations
  - `--ask-password=false`: Never prompts for passwords interactively

- **Reliability & Connection**
  - `--retries 3`: Retries the whole operation up to 3 times
  - `--low-level-retries 5`: Retries lower level operations (like HTTP requests) up to 5 times
  - `--contimeout 30s`: Connection timeout of 30 seconds
  - `--timeout 120s`: Total operation timeout of 2 minutes

- **Performance & Smart Transfer**
  - `--tpslimit 10`: Limits transactions per second to avoid OneDrive throttling
  - `--progress`: Shows progress during file transfers
  - `--update`: Only transfers files newer than existing files at destination
  - `--skip-links`: Avoids following symbolic links which can cause issues
  - `--size-only`: Compares file sizes instead of times for more reliable deduplication

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

## License

GPL-3.0