# PwnyCloud

```
   🌈 PwnyCloud 🌩️
      .--.
   .-'_\/_'-.  
   '. /\ /.'  
     "||"
      ||
      ||
```

**PwnyCloud** is a Pwnagotchi plugin that automatically backs up handshakes and related files to any cloud provider supported by [rclone](https://rclone.org/).  
It is designed for flexibility and supports a wide range of cloud storage services, including (but not limited to) OneDrive, Google Drive, Dropbox, Box, Mega, and many more.

---

## Features

- **Automatic backup** of handshakes to the cloud
- **Webhook support** for triggering backups remotely
- **Automatic backup when new handshakes are captured**
- **Status display** showing number of backed-up files
- **Supports any rclone-compatible provider**
- **Only uploads new or changed files**
- **Animated Pwnagotchi faces during upload**
- **Test mode** for dry runs
- **Reset command** to clear upload history and force full backup

---

## Supported Cloud Providers

PwnyCloud supports any service that [rclone](https://rclone.org/) supports, including:

- **Microsoft OneDrive** (tested)
- **Google Drive**
- **Dropbox**
- **Box**
- **Mega**
- **Amazon S3**
- **Backblaze B2**
- **pCloud**
- ...and many more!

See the [full list of rclone backends](https://rclone.org/overview/) for all supported services.

---

## Installation

1. **Install rclone** on your Pwnagotchi:
    ```sh
    curl https://rclone.org/install.sh | sudo bash
    ```

2. **Configure your cloud provider** with rclone (run as `sudo` to avoid permission issues):
    ```sh
    sudo rclone config
    ```
    - Follow the prompts to set up your remote (e.g., `pwnycloud`, `onedrive`, `gdrive`, etc.).
    - Make note of the remote name you choose.

3. **Copy [pwnycloud.py](http://_vscodecontentref_/1) to your plugins directory:**
    ```sh
    sudo cp pwnycloud.py /usr/local/share/pwnagotchi/custom-plugins/  # updated path for custom plugins
    ```

4. **Edit your Pwnagotchi config.toml:**
    ```toml
    main.plugins.pwnycloud.enabled = true
    main.plugins.pwnycloud.remote_name = "pwnycloud"      # or your chosen rclone remote name
    # all others optional #
    main.plugins.pwnycloud.remote_path = "handshakes"     # folder in your cloud storage
    main.plugins.pwnycloud.interval = 60                  # backup interval in seconds
    main.plugins.pwnycloud.test_mode = false              # set to true for dry run
    main.plugins.pwnycloud.min_size = 0                   # minimum file size in bytes
    main.plugins.pwnycloud.max_bw = "1M"                  # bandwidth limit (1MB/s)
    ```

---

By running `rclone config` as `sudo`, the configuration file will be created in the correct location (`/root/.config/rclone/rclone.conf`), and no additional troubleshooting steps will be required.

---

## Example: OneDrive Setup

1. **Configure OneDrive with rclone:**
    ```sh
    rclone config
    ```
    - Choose `n` for new remote, name it (e.g., `pwnycloud` or `onedrive`)
    - Select `OneDrive` as the storage type
    - Follow the prompts to authenticate

2. **Set your plugin config:**
    ```toml
    main.plugins.pwnycloud.enabled = true
    main.plugins.pwnycloud.remote_name = "onedrive"
    main.plugins.pwnycloud.remote_path = "handshakes"
    main.plugins.pwnycloud.interval = 60
    ```

---

## Example: Google Drive Setup

1. **Configure Google Drive with rclone:**
    ```sh
    rclone config
    ```
    - Choose `n` for new remote, name it (e.g., `gdrive`)
    - Select `Google Drive` as the storage type
    - Follow the prompts to authenticate

2. **Set your plugin config:**
    ```toml
    main.plugins.pwnycloud.enabled = true
    main.plugins.pwnycloud.remote_name = "gdrive"
    main.plugins.pwnycloud.remote_path = "handshakes"
    main.plugins.pwnycloud.interval = 60
    ```

---

## Using Webhooks

PwnyCloud v1.0.7 adds webhook support, allowing you to trigger backups remotely:

- **Trigger a backup**:
    ```
    http://pwnagotchi-ip:8081/plugins/pwnycloud/trigger
    ```

- **Reset upload history and trigger full backup**:
    ```
    http://pwnagotchi-ip:8081/plugins/pwnycloud/trigger?cmd=reset
    ```

- **Check status** (returns information about backup state):
    ```
    http://pwnagotchi-ip:8081/plugins/pwnycloud/trigger?cmd=status
    ```

---

## Notes

- The plugin will only upload new or changed files since the last backup.
- You can use any rclone remote name and path.
- The UI shows the number of backed-up files with an upward arrow icon.
- Automatic backup is triggered when new handshakes are captured.
- For a full list of supported cloud providers, see [rclone.org/overview](https://rclone.org/overview/).

---

## Troubleshooting

### Remote Not Found or Permission Issues
If the PwnyCloud plugin cannot find the configured `rclone` remote or you encounter permission issues, follow these steps:

1. **Verify rclone Configuration File Location**  
   Ensure the `rclone` configuration file exists at `/root/.config/rclone/rclone.conf`. Run:
   ```bash
   sudo ls -l /root/.config/rclone/rclone.conf
   ```
   If the file does not exist, it may have been created under the `pi` user instead.

2. **Copy Configuration File to Root**  
   If the configuration file exists under the `pi` user (e.g., `/home/pi/.config/rclone/rclone.conf`), copy it to the correct location for the `root` user:
   ```bash
   sudo mkdir -p /root/.config/rclone
   sudo cp /home/pi/.config/rclone/rclone.conf /root/.config/rclone.conf
   sudo chown root:root /root/.config/rclone/rclone.conf
   sudo chmod 600 /root/.config/rclone/rclone.conf
   ```

3. **Test rclone as Root**  
   Verify that the `rclone` remote is accessible by the `root` user:
   ```bash
   sudo rclone listremotes
   ```
   You should see your remote (e.g., `pwnycloud:`) listed. Then, test listing files in the remote:
   ```bash
   sudo rclone ls pwnycloud:
   ```

4. **Restart Pwnagotchi**  
   Restart the Pwnagotchi service to apply the changes:
   ```bash
   sudo systemctl restart pwnagotchi
   ```

5. **Check Plugin Logs**  
   If the issue persists, check the plugin logs for detailed error messages:
   ```bash
   cat /tmp/pwnycloud_debug.log
   ```

---

## Roadmap

Here are the planned features for upcoming releases:

### UI/UX Improvements
- Upload progress tracking with real-time feedback
- Advanced status display with upload speeds and ETA
- Visual success/failure notifications
- Configurable UI position for backup status
- Handshake count display for pending backups

### API Enhancements
- Extended webhook API with comprehensive commands
- Statistics endpoint for backup history and reporting
- Remote control for specific file operations
- Two-way sync capability to restore files from cloud storage

### Performance Optimizations
- Smarter file change detection with checksums
- Dynamic bandwidth throttling and enhanced control options
- Support for resuming interrupted uploads
- Error recovery with auto-retry for failed uploads
- Optional local file cleanup after successful upload

---

## Credits

- Plugin author: **AWWShuck**
- Inspired by the Pwnagotchi and rclone communities

---

## License

GPLv3

## Version
1.0.7

---
