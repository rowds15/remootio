# Remootio Home Assistant Integration

Complete Home Assistant integration for Remootio garage door controllers with advanced monitoring, multi-channel alerts, and automation capabilities.

## Features

### 🚪 Full Door Control
- Open/close garage door directly from Home Assistant
- Real-time door status monitoring
- WebSocket-based communication for instant updates

### 🔔 Multi-Channel Alerts
- **Push notifications** - Loud, persistent alerts on your phone
- **Email notifications** - Detailed alerts with timestamps
- **Voice announcements** - Text-to-speech alerts via smart speakers (optional)

### ⏰ Smart Monitoring
- **Left Open Alerts** - Notification when door is left open for 10+ minutes
- **Repeated Reminders** - Alerts every 5 minutes until door is closed
- **Night Alerts** - Special notifications if door opens between 10 PM - 6 AM
- **Daily Summaries** - Daily report of door activity at 9 PM
- **Auto-Stop** - All alerts stop automatically when door closes

### 📊 Activity Tracking
- Count of door openings per day
- Total time door was open per day
- Historical tracking via Home Assistant sensors

### 🎛️ Customizable
- Adjustable alert delays and intervals
- Toggle night alerts on/off
- Configurable notification channels
- Custom automation rules

## Requirements

- **Home Assistant** 2023.1 or newer
- **Remootio device** (any model with API support)
- **Home Assistant mobile app** (for push notifications)
- **Email server** (Gmail or internal SMTP server)
- **Smart speaker** (optional, for TTS announcements)

## Quick Start

### 1. Get Your Remootio API Keys

1. Open the Remootio app on your phone
2. Go to **Settings** → **API Access**
3. Enable API access
4. Note down:
   - **API Secret Key** (64-character hex string)
   - **API Auth Key** (64-character hex string)
   - **Remootio IP address** on your network

### 2. Install Custom Integration

Copy the `custom_components/remootio_custom` folder to your Home Assistant:

```bash
# Using SSH or terminal access
cp -r custom_components/remootio_custom /config/custom_components/

# Or using File Editor add-on
# Upload the entire remootio_custom folder to /config/custom_components/
```

### 3. Configure Home Assistant

Copy the configuration files from the `config/` folder and customize:

1. **configuration.yaml** - Add to your main config file
2. **automations.yaml** - Add to your automations file
3. **scripts.yaml** - Add to your scripts file

Replace all placeholder values (marked with `CHANGE THIS`) with your actual:
- Remootio IP address and API keys
- Email server settings
- Phone notification service name
- Speaker entity (if using TTS)

### 4. Restart and Test

1. Restart Home Assistant
2. Check **Developer Tools** → **States** for `cover.garage_door`
3. Test notifications using Developer Tools → Services

For detailed step-by-step instructions, see **[INSTALLATION.md](INSTALLATION.md)**

## Configuration Example

### Remootio Device
```yaml
cover:
  - platform: remootio_custom
    host: 192.168.1.100
    api_secret_key: your_64_char_secret_key_here
    api_auth_key: your_64_char_auth_key_here
    name: Garage Door
```

### Email Notifications

**Gmail:**
```yaml
notify:
  - name: email
    platform: smtp
    server: smtp.gmail.com
    port: 587
    encryption: starttls
    sender: your.email@gmail.com
    username: your.email@gmail.com
    password: your_16_char_app_password
    recipient:
      - your.email@gmail.com
```

**Internal Mail Server:**
```yaml
notify:
  - name: email
    platform: smtp
    server: 192.168.1.254
    port: 25
    encryption: none
    sender: homeassistant@yourdomain.com
    recipient:
      - you@yourdomain.com
      - family@yourdomain.com
```

## Customization

### Adjust Alert Timing

In `automations.yaml`, modify:
- Initial alert delay: `minutes: 10` (line ~16)
- Repeat interval: `minutes: 5` (line ~28)

### Night Alert Hours

Change the time window in `automations.yaml`:
```yaml
condition:
  - condition: time
    after: "22:00:00"  # 10 PM
    before: "06:00:00"  # 6 AM
```

### Add Multiple Email Recipients

In `configuration.yaml`:
```yaml
recipient:
  - first.recipient@example.com
  - second.recipient@example.com
  - third.recipient@example.com
```

### Disable Text-to-Speech

If you don't have a smart speaker, remove the TTS section from `scripts.yaml` (lines 54-64).

## Entities Created

After installation, you'll have access to:

| Entity | Type | Description |
|--------|------|-------------|
| `cover.garage_door` | Cover | Main door control (open/close/status) |
| `sensor.remootio_open_count_today` | Sensor | Number of times door opened today |
| `sensor.remootio_total_open_time_today` | Sensor | Total time door was open today |
| `input_boolean.remootio_night_alerts` | Toggle | Enable/disable night alerts |
| `input_number.remootio_alert_delay` | Number | Adjust initial alert delay |
| `input_number.remootio_repeat_interval` | Number | Adjust repeat interval |

## Automations Included

1. **Door Left Open Alert** - Primary monitoring automation
2. **Door Closed Notification** - Confirms when door closes after being open
3. **Night Opening Alert** - Special alert for nighttime activity
4. **Daily Summary** - End-of-day activity report

## Troubleshooting

### Integration Not Loading
- Check logs in **Settings** → **System** → **Logs**
- Verify `custom_components/remootio_custom` folder exists
- Ensure all three files are present: `__init__.py`, `cover.py`, `manifest.json`
- Restart Home Assistant

### Authentication Errors
- Double-check API Secret Key and Auth Key (64 characters each)
- Verify Remootio IP address is correct
- Ensure Remootio API is enabled in the app
- Check network connectivity to Remootio device

### No Push Notifications
- Verify phone notification service name (Settings → Devices & Services → Mobile App)
- Format should be: `notify.mobile_app_your_device_name`
- Test notification using Developer Tools → Services
- Ensure Home Assistant mobile app is logged in

### Email Not Working
- **Gmail**: Use app password from https://myaccount.google.com/apppasswords
- **Gmail**: Enable 2-factor authentication first
- **Internal server**: Check firewall rules and SMTP port
- Check spam/junk folder
- Review logs for SMTP errors

### Door Status Not Updating
- Check WebSocket connection in logs
- Verify Remootio device is online
- Try restarting the integration
- Check network stability between HA and Remootio

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
- API keys stored in Home Assistant configuration

## Contributing

Found a bug or have a feature request? Please open an issue on GitHub.

## License

This project is provided as-is for personal use with Remootio garage door controllers.

## Credits

- Remootio WebSocket API documentation: https://github.com/remootio/remootio-api-documentation
- Home Assistant: https://www.home-assistant.io/

## Support

For installation help, see **[INSTALLATION.md](INSTALLATION.md)**

For Claude Code users working with this repository, see **[CLAUDE.md](CLAUDE.md)**

---

**Made with ❤️ for the Home Assistant community**
