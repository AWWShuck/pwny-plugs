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
- **Supports any rclone-compatible provider**
- **Only uploads new or changed files**
- **Animated Pwnagotchi faces during upload**
- **Test mode** for dry runs
- **Configurable backup interval and remote**

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

2. **Configure your cloud provider** with rclone:
    ```sh
    rclone config
    ```
    - Follow the prompts to set up your remote (e.g., `pwnycloud`, `onedrive`, `gdrive`, etc.).
    - Make note of the remote name you choose.

3. **Copy `pwnycloud.py` to your plugins directory:**
    ```sh
    cp pwnycloud.py /usr/local/lib/python3.7/dist-packages/pwnagotchi/plugins/  # adjust path as needed
    ```

4. **Edit your Pwnagotchi config.toml:**
    ```toml
    [[plugins.pwnycloud]]
    enabled = true
    remote_name = "pwnycloud"      # or your chosen rclone remote name
    remote_path = "handshakes"     # folder in your cloud storage
    interval = 60                  # backup interval in minutes
    test_mode = false              # set to true for dry run
    ```

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
    [[plugins.pwnycloud]]
    enabled = true
    remote_name = "onedrive"
    remote_path = "handshakes"
    interval = 60
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
    [[plugins.pwnycloud]]
    enabled = true
    remote_name = "gdrive"
    remote_path = "handshakes"
    interval = 60
    ```

---

## Notes

- The plugin will only upload new or changed files since the last backup.
- You can use any rclone remote name and path.
- For a full list of supported cloud providers, see [rclone.org/overview](https://rclone.org/overview/).

---

## Credits

- Plugin author: **AWWShuck**
- Inspired by the Pwnagotchi and rclone communities

---

## License

GPLv3

---
