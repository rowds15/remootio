# Remootio Installation Guide

Complete step-by-step instructions to install and configure the Remootio integration with Home Assistant.

## Prerequisites Checklist

Before starting, collect this information:

- ✅ **Home Assistant is running** - Version 2023.1 or newer
- ✅ **Home Assistant File Editor** installed (Settings → Add-ons)
- ✅ **Remootio API enabled** - Enabled in Remootio mobile app
- 📝 **Remootio IP address**: `192.168.___._____`
- 📝 **API Secret Key**: `________________________________` (64 characters)
- 📝 **API Auth Key**: `________________________________` (64 characters)
- 📝 **Phone notify service**: `notify.mobile_app___________`
- 📝 **Email address**: `___________@_________`
- 📝 **Email server details** (Gmail or internal server)
- 📝 **Speaker entity** (optional): `media_player._________`

---

## Part 1: Get Remootio API Keys

### Step 1: Enable API in Remootio App

1. Open the **Remootio mobile app**
2. Tap **☰ Menu** → **Settings**
3. Tap **API Access**
4. Enable **API Access** toggle
5. Note down:
   - **API Secret Key** (64-character hex string)
   - **API Auth Key** (64-character hex string)

### Step 2: Find Remootio IP Address

**Method 1 - Router:**
1. Log into your router admin page
2. Look for connected devices / DHCP leases
3. Find device named "Remootio" or look for the MAC address
4. Note the IP address (e.g., `192.168.1.100`)

**Method 2 - Remootio App:**
1. Open Remootio app
2. **Settings** → **Device Information**
3. Look for "IP Address"

**Tip:** Set a static IP or DHCP reservation for your Remootio device to prevent the IP from changing.

---

## Part 2: Find Home Assistant Services

### Step 3: Find Your Phone Notification Service

1. In Home Assistant, go to **Settings** → **Devices & Services** → **Integrations**
2. Find **"Mobile App"** integration
3. Click on it
4. Look for your device name (e.g., "Pixel 10 Pro", "John's iPhone")
5. The notify service format is: `notify.mobile_app_<device_name_lowercase_with_underscores>`
   - Example: "Pixel 10 Pro" → `notify.mobile_app_pixel_10_pro`
   - Example: "John's iPhone" → `notify.mobile_app_johns_iphone`
6. **Write it down**: `notify.mobile_app___________`

### Step 4: Prepare Email Configuration

**Option A - Gmail:**
1. Go to: https://myaccount.google.com/apppasswords
2. **Note:** You must have 2-factor authentication enabled
3. Create app password for "Mail"
4. Copy the 16-character password (spaces will be removed automatically)
5. **Write down:**
   - Email: `___________@gmail.com`
   - App password: `________________`

**Option B - Internal Mail Server:**
1. Get your internal mail server details:
   - Server IP: `192.168.___.___`
   - Port: Usually `25` for internal servers
   - Encryption: Usually `none` for internal servers
2. **Write down:**
   - Server: `___________`
   - Port: `___`
   - Sender email: `___________@___________`

---

## Part 3: Install Custom Integration

### Step 5: Upload Custom Integration Files

**Method 1 - File Editor Add-on (Recommended):**

1. In Home Assistant, open **File Editor**
2. Click the **📁 folder icon** in the top-left
3. Navigate to `/config/`
4. Create folder structure:
   - Click **📁 Create Folder** → Name it `custom_components`
   - Inside `custom_components`, create folder `remootio_custom`
5. Upload these three files to `/config/custom_components/remootio_custom/`:
   - From this repository's `custom_components/remootio_custom/`:
     - `__init__.py`
     - `cover.py`
     - `manifest.json`

**Method 2 - SSH/Terminal:**

```bash
# If you have SSH access to your Home Assistant
cd /config
mkdir -p custom_components/remootio_custom
# Then copy the three files from this repo to that directory
```

**Method 3 - Samba/Network Share:**

1. Connect to Home Assistant via network share
2. Navigate to `config` folder
3. Create `custom_components/remootio_custom/` folders
4. Copy the three files there

### Step 6: Verify Files

Your directory structure should look like:
```
/config/
└── custom_components/
    └── remootio_custom/
        ├── __init__.py
        ├── cover.py
        └── manifest.json
```

---

## Part 4: Configure Home Assistant

### Step 7: Edit configuration.yaml

1. Open **File Editor** in Home Assistant
2. Open `/config/configuration.yaml`
3. Scroll to the **very bottom** of the file
4. Copy the contents from this repository's `config/configuration.yaml`
5. Paste at the bottom of your `configuration.yaml`
6. **Replace these placeholder values:**

   | Placeholder | Replace With | Where to Find |
   |------------|--------------|---------------|
   | `192.168.1.100` | Your Remootio IP | Step 2 |
   | `YOUR_SECRET_KEY` | 64-char API Secret Key | Step 1 |
   | `YOUR_AUTH_KEY` | 64-char API Auth Key | Step 1 |
   | `smtp.gmail.com` | Your mail server | Step 4 |
   | `587` | Your mail port | Step 4 (Gmail: 587, Internal: 25) |
   | `starttls` | Encryption type | Step 4 (Gmail: starttls, Internal: none) |
   | `your.email@gmail.com` | Your email | Step 4 |
   | `YOUR_16_CHAR_APP_PASSWORD` | Gmail app password | Step 4 (skip if internal server) |

7. **Save** the file

**Note:** If you already have these sections in your `configuration.yaml`, merge the new content with existing:
- `notify:` - Add the new email notifier to your existing notify list
- `cover:` - Add the Remootio cover to your existing covers
- `sensor:`, `input_number:`, `input_boolean:` - Add to existing sections

### Step 8: Edit scripts.yaml

1. Open `/config/scripts.yaml` in File Editor
2. Scroll to the **very bottom**
3. Copy the contents from this repository's `config/scripts.yaml`
4. Paste at the bottom
5. **Replace these values:**
   - `notify.mobile_app_your_phone` (appears 2 times) → Your phone service from Step 3
   - `media_player.your_speaker` → Your speaker entity, or **delete lines 54-64** if no speaker
6. **Save** the file

### Step 9: Edit automations.yaml

1. Open `/config/automations.yaml` in File Editor
2. Scroll to the **very bottom**
3. Copy the contents from this repository's `config/automations.yaml`
4. Paste at the bottom
5. **Replace these values:**
   - Find: `notify.mobile_app_your_phone` (appears 4 times)
   - Replace with: Your phone service from Step 3
6. **Save** the file

**Important:** If your `automations.yaml` is empty or starts with `[]`, remove the `[]` and paste the automation content directly.

---

## Part 5: Validate and Start

### Step 10: Check Configuration

1. Go to **Developer Tools** → **YAML**
2. Click **"Check Configuration"**
3. Should say **"Configuration valid!"**

**If errors appear:**
- Check YAML indentation (use spaces, not tabs)
- Verify all placeholder values are replaced
- Look for typos in email addresses or API keys
- Check that curly quotes (`""`) aren't used instead of straight quotes (`""`)

### Step 11: Restart Home Assistant

1. **Settings** → **System** → **Restart**
2. Click **"Restart Home Assistant"**
3. Wait about 1-2 minutes for the system to restart

### Step 12: Verify Integration Loaded

1. Go to **Developer Tools** → **States**
2. Search for `cover.garage_door`
3. Should see the entity with state `open`, `closed`, or `unknown`

**If entity doesn't appear:**
- Check **Settings** → **System** → **Logs** for errors
- Verify custom integration files are in correct location
- Ensure Remootio IP address is correct and device is online
- Check API keys are exactly 64 characters

---

## Part 6: Test Everything

### Step 13: Test Door Control

1. **Developer Tools** → **States**
2. Find `cover.garage_door`
3. Click on it
4. Try **"Open Cover"** or **"Close Cover"**
5. Door should respond

**If not working:**
- Check Remootio device logs in the mobile app
- Verify API keys are correct
- Check network connectivity
- Review Home Assistant logs

### Step 14: Test Push Notification

1. **Developer Tools** → **Services**
2. Service: `notify.mobile_app_your_phone` (use your actual service name)
3. Service data:
   ```yaml
   message: "Test notification from Home Assistant"
   title: "Test Alert"
   data:
     priority: high
     channel: alarm_stream
   ```
4. Click **"Call Service"**
5. You should receive a **loud notification** on your phone

**If not working:**
- Verify service name is exactly correct
- Check Home Assistant mobile app is logged in
- Test with a simpler notification first (without data fields)
- Check phone notification settings

### Step 15: Test Email Notification

1. **Developer Tools** → **Services**
2. Service: `notify.email`
3. Service data:
   ```yaml
   message: "Test email from Home Assistant Remootio system"
   title: "Test Email"
   ```
4. Click **"Call Service"**
5. Check your email inbox (and spam folder)

**If not working:**
- **Gmail**: Verify you used app password (not regular password)
- **Gmail**: Check 2FA is enabled on Google account
- **Internal server**: Verify server address and port
- Check **Settings** → **System** → **Logs** for SMTP errors

### Step 16: Test Text-to-Speech (Optional)

If you configured a speaker:

1. **Developer Tools** → **Services**
2. Service: `tts.google_translate_say`
3. Service data:
   ```yaml
   entity_id: media_player.your_speaker
   message: "This is a test announcement from your garage door monitor"
   ```
4. Click **"Call Service"**
5. You should hear the message from your speaker

### Step 17: Test Full Alert System

**Quick test with 1-minute delay:**

1. Open `/config/automations.yaml` in File Editor
2. Find the first automation (`remootio_door_open_alert`)
3. Change `minutes: 10` to `minutes: 1` (around line 16)
4. **Save** the file
5. **Developer Tools** → **YAML** → **"Reload Automations"**
6. **Open your garage door** using Home Assistant
7. Wait 1 minute
8. You should receive:
   - ✅ Push notification (loud)
   - ✅ Email notification
   - ✅ Voice announcement (if speaker configured)
9. Wait another 5 minutes - you should get a repeat alert
10. **Close the door** - alerts should stop
11. **Important:** Change back to `minutes: 10` and reload automations

---

## Part 7: Customize (Optional)

### Adjust Alert Timing

In `/config/automations.yaml`:
- **Initial alert delay**: Line ~16: `minutes: 10` (change to desired minutes)
- **Repeat interval**: Line ~28: `minutes: 5` (how often to repeat)

After changes: **Developer Tools** → **YAML** → **"Reload Automations"**

### Add Multiple Email Recipients

In `/config/configuration.yaml`:
```yaml
recipient:
  - first.recipient@example.com
  - second.recipient@example.com
  - third.recipient@example.com
```

After changes: **Restart Home Assistant**

### Change Night Alert Hours

In `/config/automations.yaml`, find `remootio_night_opening_alert`:
```yaml
condition:
  - condition: time
    after: "22:00:00"  # 10 PM - change this
    before: "06:00:00"  # 6 AM - change this
```

### Adjust Notification Sound

**Android:**
- Notification volume is controlled by **Alarm volume** on your phone
- Turn up alarm volume for louder alerts

**iOS:**
- Go to **iOS Settings** → **Notifications** → **Home Assistant**
- Choose notification sound
- Enable "Critical Alerts" if available

### Dashboard Controls

The input helpers create UI controls you can add to your dashboard:
- `input_boolean.remootio_night_alerts` - Toggle night alerts on/off
- `input_number.remootio_alert_delay` - Adjust delay via slider
- `input_number.remootio_repeat_interval` - Adjust repeat interval via slider

Add to dashboard via **Edit Dashboard** → **Add Card** → **Entities Card**

---

## Troubleshooting

### "Configuration invalid" Error

1. Check **Settings** → **System** → **Logs** for specific error message
2. Common issues:
   - YAML indentation wrong (use 2 spaces, not tabs)
   - Missing colons or quotes
   - Pasted in wrong location (must be at bottom, not middle of other sections)
   - Curly quotes instead of straight quotes

### Integration Not Loading

1. Verify folder structure: `/config/custom_components/remootio_custom/`
2. Check all three files are present: `__init__.py`, `cover.py`, `manifest.json`
3. Review logs for Python errors
4. Restart Home Assistant completely

### Authentication Errors

1. Verify API keys are exactly 64 characters (hex)
2. Check no extra spaces before/after keys
3. Ensure API is enabled in Remootio app
4. Verify Remootio device is online and reachable
5. Try disabling and re-enabling API in Remootio app

### No Push Notifications

1. Verify phone notify service name is exact match
2. Test with simple notification first
3. Check Home Assistant app is logged in on phone
4. Verify notification permissions are granted
5. Try reinstalling Home Assistant mobile app

### No Email

1. **Gmail users:**
   - Must use app password, not regular password
   - Must have 2FA enabled first
   - Check spam/junk folder
2. **Internal server users:**
   - Verify server is reachable from Home Assistant
   - Check firewall rules allow port 25
   - Try `encryption: none` for internal servers
3. Check logs for SMTP errors

### Notifications Not Loud Enough

- **Android**: Turn up **Alarm volume** (not media or ringer)
- **iOS**: iOS doesn't support alarm-level notifications from HA
  - Consider relying on email and TTS instead
  - Or use Pushover/Pushbullet for critical alerts

### Door Status Wrong

1. Open Remootio mobile app - verify status there
2. Check WebSocket connection in HA logs
3. Try closing and reopening the door manually
4. Reload integration: **Settings** → **System** → **Restart**

---

## What You Get

After successful installation, you have:

✅ **Full door control** via Home Assistant dashboard
✅ **Automatic alerts** when door left open 10+ minutes
✅ **Repeated reminders** every 5 minutes while open
✅ **Multi-channel notifications** (push, email, voice)
✅ **Night monitoring** (10 PM - 6 AM alerts)
✅ **Daily summaries** sent at 9 PM
✅ **Activity tracking** (open count, total time open)
✅ **Customizable** alert timing and behaviors

---

## Quick Reference Commands

### Test Notification
```yaml
service: notify.mobile_app_your_phone
data:
  message: "Test message"
  title: "Test"
  data:
    priority: high
    channel: alarm_stream
```

### Close Door Manually
```yaml
service: cover.close_cover
target:
  entity_id: cover.garage_door
```

### Reload After Config Changes
- **Automations**: Developer Tools → YAML → Reload Automations
- **Scripts**: Developer Tools → YAML → Reload Scripts
- **Everything else**: Settings → System → Restart

---

## Need Help?

1. Check **Settings** → **System** → **Logs** for error messages
2. Review this guide's Troubleshooting section
3. Verify all prerequisites are met
4. Test each component individually
5. Open an issue on GitHub with:
   - Home Assistant version
   - Error messages from logs
   - Steps you've already tried

---

**Installation complete! Enjoy your smart garage door monitoring system.**
