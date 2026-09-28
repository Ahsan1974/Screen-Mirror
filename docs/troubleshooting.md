# Troubleshooting

The laptop log is `logs/phone_remote.log`. The phone shows the same kind of lines at the bottom of the app. Match the times when something fails.

## No phone found

```text
No phone found.

Make sure:
✓ Phone Wi-Fi is ON
✓ Laptop Wi-Fi is ON
✓ Both are connected to the same network
✓ Android application is running
```

Also check:

- The phone app is open and the log says `Listening on 192.168.x.x:8765`. If the IP is `unknown`, the phone is not on Wi-Fi.
- You are not on a guest SSID, and "AP isolation" or "client isolation" is off in the router. Isolation lets both devices use the internet and still blocks them from seeing each other.
- A VPN is off on both devices. A VPN often hides LAN addresses.
- Windows Firewall allowed Python on private networks. UDP 5353 is mDNS. TCP 8765 is the session.
- The laptop and phone are in the same subnet. `192.168.1.20` and `192.168.0.20` are different networks unless the router bridges them.
- Discovery can fail even when a direct connection works. Type the IP from the phone into Manual connection.

The manual field refuses public addresses and host names. That is intentional.

## Pairing failed

```text
Pairing failed.
Please try again.
```

The code on the laptop and the code you type must be the same six digits. After five wrong tries the socket closes and a new code is shown on the next connection. If you already paired and replaced the phone app, press Forget paired phone on the laptop, and Forget laptop on the phone, then pair again.

## Screen capture permission is required

```text
Screen capture permission is required.

Open the Android application and allow screen capture.
```

The socket is up, but you have not pressed Start screen sharing, or you dismissed Android's dialog. Press Start screen sharing and accept it. The laptop picture starts when the first JPEG arrives. You will see the system cast icon and the red banner. If you do not, sharing is not on.

If Android says the capture token could not be created, press Start again while the Phone Remote activity is on screen. Do not switch away before accepting the dialog.

## The picture is connected but clicks do nothing

The accessibility service is off, or Android blocked it as a restricted setting. Open the phone app. If it says `Accessibility: off`, follow `docs/android_permissions.md`. The laptop banner repeats the same instruction.

Viewing does not require accessibility. Control does.

## Typing does not appear

Tap a normal text field on the phone first, so it has focus. Then click the laptop picture so the laptop window has keyboard focus, and type.

If the field is a game, a canvas, or a browser box that hides its text, Android will not accept `ACTION_SET_TEXT`. The laptop reports that. Use the on-screen keyboard on the phone for that field. This app will not bypass that.

Escape goes Back. It does not send Escape to the app.

## Connection lost

```text
Connection lost.

Attempting to reconnect...
```

The laptop retries every two seconds until you press Disconnect, as long as reconnect is enabled in Settings. When the phone is reachable again with the same token, the session returns without a new code.

If it never returns, the phone app was swiped away and the vendor killed the service, or the IP changed and discovery has not caught up. Open the phone app, read the IP, and connect manually if needed.

## Colors look wrong

On the phone, enable "Swap red and blue if the picture looks wrong". A few devices hand the capturer bytes in the opposite order. The next frames use the swap. Leave it off when the colors are already right.

## File transfer

- The picture pauses during a transfer. That is deliberate.
- A checksum or size mismatch deletes the partial file and reports an error. Send it again.
- On the phone, look in the Downloads app under `PhoneRemote`.
- On the laptop, look in the project's `downloads` folder. The status line shows the full path when a receive finishes.
- One transfer at a time. Wait until the bar reaches the end before starting another.

## Clipboard

If the laptop says Android blocked a background read, open the phone app and press Send clipboard to laptop. Copy on the laptop still flows to the phone when auto-sync is on. Turn auto-sync off in Settings if you do not want passwords you copy to be sent across the Wi-Fi.

## The phone app disappears after the screen locks

Open the vendor's battery or autostart settings and allow Phone Remote. Also press Allow running in the background inside the app. Keep the notification. Force-stop from the system app settings ends the session until you open the app again.

## Port already in use

The phone log says it could not listen. Another app is using 8765, or a previous process has not exited. Press Quit in the app, open it again, or change the port on the phone and enter that same port in the laptop's manual connection. Discovered phones advertise the port they are actually using, so the manual port is only a fallback.

## Protocol mismatch

Update both apps together. This version speaks protocol 1. An older build is rejected instead of half-connecting.
