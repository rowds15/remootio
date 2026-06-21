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

The integration will validate your connection and create all entities automatically.

## Entities Created

After setup, you'll have the following entities:

| Entity | Type | Description |
|--------|------|-------------|
| `cover.garage_door_channel_1` | Cover | Channel 1 — open/close control with status |
| `button.garage_door_toggle_channel_1` | Button | Channel 1 toggle (Android Auto / CarPlay) |
| `button.garage_door_toggle_channel_2` | Button | Channel 2 trigger (Android Auto / CarPlay) |
| `sensor.garage_door_operation_count_channel_1` | Sensor | Number of times channel 1 has opened |
| `sensor.garage_door_last_opened_channel_1` | Sensor | Timestamp of last channel 1 open |
| `sensor.garage_door_last_closed_channel_1` | Sensor | Timestamp of last channel 1 close |

The device will appear in your Device Registry with manufacturer "Remootio" and model "Garage Door Controller".

### Dual-output devices (e.g. Remootio 3)

Remootio 3 supports two independent control outputs (e.g. a "full open" and a "walk/partial open" connection). The Remootio WebSocket API uses separate action types for each output (`TRIGGER` for the primary, `TRIGGER_SECONDARY` for the secondary) and provides no queryable state for the secondary output.

For this reason, **Channel 2 is exposed as a button only** — pressing it fires `TRIGGER_SECONDARY` on the device, identical to pressing the second button in the Remootio app. Channel 1 remains a full cover entity with open/closed state tracking.

## Android Auto / CarPlay

The integration includes **Toggle button** entities that work with Android Auto and CarPlay through the Home Assistant Companion App.

### Setup for Android Auto

1. Install the **Home Assistant Companion App** on your Android phone
2. Open the app and go to **Settings** > **Companion App** > **Android Auto**
3. Enable Android Auto integration
4. Add `button.garage_door_toggle_channel_1` (and/or channel 2) to your favorites
5. The button will appear in Android Auto when connected to your car

### Setup for CarPlay

1. Install the **Home Assistant Companion App** on your iPhone
2. Open the app and go to **Settings** > **Companion App** > **CarPlay**
3. Configure which entities appear in CarPlay
4. Add `button.garage_door_toggle_channel_1` (and/or channel 2)
5. The button will appear in CarPlay when connected to your car

**Note:** The toggle buttons send a TRIGGER (channel 1) or TRIGGER_SECONDARY (channel 2) command — identical to pressing the corresponding button in the Remootio app.

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

### No Entities After Update

After updating integration files on disk, Home Assistant must be **fully restarted** (not just reload the integration or remove/re-add it) to load the new code. Remove and re-add the integration only after restarting HA.

### Door Status Not Updating

The integration maintains a persistent WebSocket connection that receives `StateChange` events in real time (no polling delay). If the connection drops, it reconnects automatically with exponential backoff — you should see door state update within seconds of a reconnect without any manual intervention.

If state stops updating:
- Check Home Assistant logs for `remootio` — reconnect attempts are logged at warning level
- Verify the Remootio device is online and reachable on port 8080
- A 30-second polling fallback is always active, so state will self-correct even if the event listener is temporarily down
- If the issue persists after several minutes, restart Home Assistant and remove/re-add the integration

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
- `local_push` integration: a persistent authenticated WebSocket connection receives `StateChange` events in real time; 30-second polling runs as a fallback
- Automatic reconnection with exponential backoff (5s → 10s → … → 60s cap); replayed events from the device's 100-event buffer are deduplicated by event counter

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
