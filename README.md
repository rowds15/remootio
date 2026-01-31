# Remootio Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Complete Home Assistant integration for Remootio garage door controllers with UI-based configuration, device registry support, and advanced monitoring capabilities.

## Features

### Full Door Control
- Open/close garage door directly from Home Assistant
- Real-time door status monitoring
- WebSocket-based communication for instant updates
- **Toggle button** for Android Auto / CarPlay compatibility

### Modern Integration
- **UI-based setup** - Configure via Home Assistant's Integrations page
- **HACS support** - Easy installation and updates
- **Device Registry** - Proper device and entity management
- **Reconfiguration** - Update settings without removing the integration

### Multi-Channel Alerts (via automations)
- **Push notifications** - Loud, persistent alerts on your phone
- **Email notifications** - Detailed alerts with timestamps
- **Voice announcements** - Text-to-speech alerts via smart speakers

### Smart Monitoring (via automations)
- **Left Open Alerts** - Notification when door is left open
- **Night Alerts** - Special notifications for nighttime activity
- **Daily Summaries** - Daily report of door activity

## Requirements

- **Home Assistant** 2023.1 or newer
- **Remootio device** (any model with API support)
- **HACS** (Home Assistant Community Store) - for easy installation

## Installation

### Option 1: HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Add"
6. Search for "Remootio" in HACS
7. Click "Download"
8. Restart Home Assistant

### Option 2: Manual Installation

1. Download the latest release
2. Copy the `custom_components/remootio` folder to your Home Assistant's `custom_components` directory
3. Restart Home Assistant

## Configuration

### 1. Get Your Remootio API Keys

1. Open the Remootio app on your phone
2. Go to **Settings** > **API Access**
3. Enable API access
4. Note down:
   - **API Secret Key** (64-character hex string)
   - **API Auth Key** (64-character hex string)
   - **Remootio IP address** on your network

### 2. Add the Integration

1. Go to **Settings** > **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Remootio"
4. Enter your device details:
   - **Host/IP Address**: Your Remootio device's IP (e.g., `192.168.1.100`)
   - **API Secret Key**: 64-character hex string from the app
   - **API Auth Key**: 64-character hex string from the app
   - **Device Name**: A friendly name (e.g., "Garage Door")
5. Click **Submit**

The integration will validate your connection and create the cover entity.

## Entities Created

After setup, you'll have:

| Entity | Type | Description |
|--------|------|-------------|
| `cover.garage_door` | Cover | Main door control (open/close/status) |
| `button.garage_door_toggle` | Button | Toggle button for Android Auto / CarPlay |

The device will appear in your Device Registry with manufacturer "Remootio" and model "Garage Door Controller".

## Android Auto / CarPlay

The integration includes a **Toggle button** entity that works with Android Auto and CarPlay through the Home Assistant Companion App.

### Setup for Android Auto

1. Install the **Home Assistant Companion App** on your Android phone
2. Open the app and go to **Settings** > **Companion App** > **Android Auto**
3. Enable Android Auto integration
4. Add the `button.garage_door_toggle` entity to your Android Auto favorites
5. The button will appear in Android Auto when connected to your car

### Setup for CarPlay

1. Install the **Home Assistant Companion App** on your iPhone
2. Open the app and go to **Settings** > **Companion App** > **CarPlay**
3. Configure which entities appear in CarPlay
4. Add the `button.garage_door_toggle` entity
5. The button will appear in CarPlay when connected to your car

**Note:** The toggle button sends a TRIGGER command to the Remootio device, which opens the door if closed or closes it if open (same behavior as the physical button).

## Automations

The integration provides the cover entity. For advanced features like alerts and monitoring, set up automations.

### Example: Door Left Open Alert

```yaml
automation:
  - alias: "Garage Door Left Open Alert"
    trigger:
      - platform: state
        entity_id: cover.garage_door
        to: "open"
        for:
          minutes: 10
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Garage Door Alert"
          message: "The garage door has been open for 10 minutes!"
```

### Example: Night Opening Alert

```yaml
automation:
  - alias: "Garage Door Night Opening"
    trigger:
      - platform: state
        entity_id: cover.garage_door
        to: "open"
    condition:
      - condition: time
        after: "22:00:00"
        before: "06:00:00"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Night Alert"
          message: "Garage door opened at {{ now().strftime('%H:%M') }}"
```

## Reconfiguring

To update your device settings:

1. Go to **Settings** > **Devices & Services**
2. Find the Remootio integration
3. Click the three dots menu
4. Select **Reconfigure**
5. Update your settings and click **Submit**

## Troubleshooting

### Integration Not Found

- Ensure you've restarted Home Assistant after installation
- Check that the `custom_components/remootio` folder exists with all files

### Cannot Connect

- Verify the IP address is correct and the device is online
- Ensure the Remootio device and Home Assistant are on the same network
- Check that WebSocket port 8080 is not blocked

### Invalid API Keys

- Double-check the API Secret Key and Auth Key (64 characters each)
- Regenerate the keys in the Remootio app if needed
- Ensure you haven't swapped the Secret and Auth keys

### Door Status Not Updating

- Check WebSocket connection in Home Assistant logs
- Verify the Remootio device is online
- Try removing and re-adding the integration

### Logs

Enable debug logging by adding to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.remootio: debug
```

## Technical Details

### Communication Protocol
- Uses Remootio WebSocket API v3
- AES-CBC encryption with PKCS7 padding
- HMAC-SHA256 authentication
- Challenge-response authentication flow
- Session-based encryption keys

### Dependencies
- `cryptography` (included in Home Assistant Core)
- `websockets` (included in Home Assistant Core)

### Security
- All communication encrypted with AES-256
- MAC validation on all frames
- Local network only (no cloud required)
- API keys stored securely in Home Assistant

## Migration from YAML Configuration

If you were using the previous YAML-based configuration (`remootio_custom`):

1. Remove the old configuration from `configuration.yaml`
2. Delete the `custom_components/remootio_custom` folder
3. Install this integration via HACS or manually
4. Set up via the UI as described above
5. Update any automations to use the new entity IDs (e.g., `cover.garage_door`)

## Contributing

Found a bug or have a feature request? Please open an issue on GitHub.

## License

This project is provided as-is for personal use with Remootio garage door controllers.

## Credits

- Remootio WebSocket API documentation: https://github.com/remootio/remootio-api-documentation
- Home Assistant: https://www.home-assistant.io/
