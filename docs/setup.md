# Setup

You need your own Android phone and your own laptop on the same Wi-Fi. A guest network that blocks devices from seeing each other will not work. Turn off any VPN on both devices while you use this.

## Laptop

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/). On the installer, enable "Add python.exe to PATH".
2. Open a terminal in this project folder.

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python laptop/main.py
```

On macOS or Linux the virtual environment is activated with `source venv/bin/activate`.

The first launch creates:

- `config.yaml` is already in the project. Edit `device_name` if you want the phone to show a different laptop name.
- `data/paired_devices.json` after the first run. This file holds the pairing token. It is git-ignored.
- `logs/phone_remote.log`
- `downloads/` for files the phone sends you.

Windows Firewall may ask whether Python may communicate on private networks. Allow it on private networks only. Do not allow it on public networks.

Dependencies, all free:

| Package | Why it is here |
| --- | --- |
| PySide6 | The window, and JPEG decoding |
| websockets | The laptop's WebSocket client |
| zeroconf | Finding the phone with mDNS |
| PyYAML | Reading `config.yaml` |

OpenCV, NumPy, and Pillow are not installed. PySide6 already decodes the JPEG frames.

### Tests without a phone

From the project folder, with the virtual environment active:

```powershell
python -m unittest discover -s tests -v
```

Those tests cover discovery filtering, pairing, reconnect, the binary headers, and file reassembly. They do not capture a real screen. Screen, touch, and clipboard need the phone.

## Android

Install `PhoneRemote.apk` (version 1.3 or newer) on the phone. The laptop app can show a local install page, such as `http://192.168.100.28:8088`, which you open in the phone’s Chrome browser. Do not send the APK through WhatsApp. If Google Play Protect blocks it, turn off Scan apps with Play Protect, install, then turn the scan back on. Version 1.2 adds the browser page the office laptop uses. Install that update over the existing app.

The emulator cannot join this Wi-Fi session. Use the real phone.

## First connection

1. Connect the phone and the laptop to the same Wi-Fi. Forget any VPN.
2. Open Phone Remote on the phone. Allow notifications when Android asks. The screen shows an IP such as `192.168.1.20` and says it is listening.
3. Open the laptop app. Within a few seconds the phone should appear under Available devices. If it does not, type that IP into Manual connection and press Connect. The port is `8765` unless you changed it on the phone.
4. The laptop shows a 6-digit code. On the phone, type that code and press Pair.
5. On the phone, press Start screen sharing and accept Android's system dialog. The cast icon and the red banner mean the screen is being viewed. That is deliberate.
6. For touch and keyboard, press Enable accessibility. Android opens the system list. Find Phone Remote and turn it on. On Android 13 and newer, a sideloaded app may be blocked until you open the app's App info page, use the menu, and tap Allow restricted settings. Then go back and enable the service.
7. Press Allow running in the background and accept the system prompt so the session is less likely to be killed.
8. Click the phone picture on the laptop, then type. Use Back, Home, and Recents under the picture.

The next connection skips the code. The token is remembered until you press Forget on either side.

## Office laptop, browser only

Use this when the other computer should not have Python installed.

1. Put the phone and that laptop on the same Wi-Fi. Turn VPNs off.
2. Open Phone Remote. It shows a line such as `http://192.168.100.35:8080`.
3. On the office laptop, open that address in Chrome. You can also open the public site and type the phone IP there. The browser then leaves the public site and opens the phone.
4. The page shows a 6-digit code. Type it on the phone and tap Pair.
5. On the phone, start screen sharing if it is not already on. Accessibility can stay on from the earlier setup.
6. Click the picture, type, and use Back, Home, and Recents. Use the header button to switch light and dark. Use Send to phone for clipboard text.

The Python window on the computer where this project lives still works. Only one of them can be connected at a time.

## ChatGPT

ChatGPT's reply box does not accept normal remote typing. Do this once on the phone:

1. In Phone Remote, tap Enable Phone Remote keyboard. Turn Phone Remote on in the keyboard list.
2. Tap Switch to Phone Remote keyboard and choose it.
3. On the laptop, tap the reply box in the mirrored screen so the green "Typing from your laptop" strip appears.
4. Write the message in the laptop's ChatGPT box and press Send into the phone. Enter sends it. Copy chat brings the visible conversation back to the laptop.

Install the 1.3 phone update before this works. Open the address shown by the laptop app in the phone's Chrome browser.

## Settings

Laptop: Settings in the window writes `config.yaml`.

- Device name is what the phone shows while pairing.
- Max width and max height are a box. The phone does not stretch the picture.
- Frames per second is limited to 5–30. 15 is the default.
- Quality is low (40), medium (60), or high (80).
- Reconnect retries every 2 seconds after a drop until you press Disconnect.
- Clipboard auto-sync copies laptop clipboard text to the phone while you are connected.

Phone:

- The name is the mDNS name.
- The port is saved immediately when you leave the field. If the new port does not listen, the log says so.
- Swap red and blue is only for a device whose captured colors look reversed.

## Where files go

- Laptop to phone: drag a file onto the phone picture, or press Transfer file. The phone saves it in `Downloads/PhoneRemote` on Android 10 and newer. Older phones save it in the app's own download folder and the log shows the path.
- Phone to laptop: Send a file to the laptop. The laptop asks before writing. Accepted files land in the project's `downloads` folder.

A transfer pauses the live picture until it finishes.
