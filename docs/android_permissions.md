# Android permissions and limits

Every capability below is a normal Android API. The app does not root the phone, hide its notification, or turn on accessibility by itself. If a permission is missing, that feature stops and the other features keep working.

Minimum version is Android 8 (API 26). The project targets Android 14 (API 34).

## Screen capture

Permission: the system MediaProjection dialog, plus the `FOREGROUND_SERVICE_MEDIA_PROJECTION` service type.

What you do: press Start screen sharing and accept the dialog. Android shows its own cast indicator. The app also shows a red banner, "Your screen is being viewed by …", and a notification with Stop sharing.

Limits:

- Android makes you accept the dialog again each time sharing starts. The token cannot be saved and reused. That is an Android rule.
- Stopping the cast chip, or pressing Stop sharing, ends capture. The socket can stay up.
- The picture includes the status bar and navigation bar. It does not include secure windows such as some payment screens; Android blanks those.
- Capture runs only while the capture service is in the foreground. If the phone kills that service, press Start screen sharing again.

## Touch, keyboard, Back, Home, Recents

Permission: the Phone Remote accessibility service. You enable it under Settings, Accessibility. The service declares `canPerformGestures` and `canRetrieveWindowContent`.

What it is allowed to do:

- Dispatch gestures, which is how a left click, drag, and long press are implemented.
- Read the focused editable field and replace its text, which is how typing works.
- Perform the global Back, Home, and Recents actions.

What you do:

1. In the app, press Enable accessibility.
2. In the system list, open Phone Remote and turn it on.
3. On Android 13 and newer, if the switch is disabled: open Settings, Apps, Phone Remote, tap the menu, tap Allow restricted settings, then return to Accessibility and turn the service on.

The service description tells you that it can see the focused field in order to type. It does not send the UI tree to the laptop. Only the screen JPEGs, the files you choose, and clipboard text you sync are sent.

Limits, stated plainly:

- With the service off, you can still view the screen. You cannot click, type, or press Back, Home, or Recents. There is no second, hidden API this app will call instead.
- Typing works in fields that expose themselves as editable to accessibility. Many games, some browsers, and custom-drawn views do not. The laptop shows "This field does not accept typing".
- Escape on the laptop performs Back. Android does not allow this app to inject a real Escape key.
- Right-click is a long press, which is how Android opens many context menus. It is not a mouse right-click, because the phone has no mouse button.
- Arrow keys move the cursor only when the field supports accessibility movement or a selection index. Some fields ignore both.
- A drag is a gesture, so very fast swipes can be simplified. Clicks and short drags are the reliable case.

## Notifications

Permission: `POST_NOTIFICATIONS` on Android 13 and newer. The app asks on launch.

The connection service notification must stay. It is how you can see that the socket is alive, and how Android lets the process keep running. Do not disable the Phone Remote notification channel if you want the session to survive leaving the app.

## Local network

Permissions: `INTERNET` (Android requires this even for a LAN socket), Wi-Fi state, and multicast. The multicast lock keeps mDNS from being dropped while the phone sleeps lightly.

The server binds all interfaces so it can be reached when the Wi-Fi address changes, then closes any client whose source address is not a private LAN address. Do not add a port-forward on the router. A forwarded connection arrives with a public source address and is rejected, but you should still not create the forward.

## Clipboard

No extra permission. Writing the clipboard from the service works while the app is in the foreground service. Reading it from the background does not, starting with Android 10. Android may also toast that an app read the clipboard.

Phone to laptop: open the app and press Send clipboard to laptop.
Laptop to phone: copy on the laptop while connected, if auto-sync is on, or use the Clipboard button.

## Files

No storage permission.

- Sending from the phone uses the system document picker.
- Receiving on Android 10 and newer uses the MediaStore downloads collection, folder `Download/PhoneRemote`.
- On Android 8 and 9 the file is stored in the app-specific download directory and the log shows the path.

## Battery

The app asks, through the system dialog, to ignore battery optimizations. You can refuse. Some phones, especially Xiaomi, Oppo, Vivo, and Huawei, still kill background work until you also allow autostart in the vendor settings. If the session dies when the screen locks, that vendor setting is the first place to look.

The phone holds a partial wake lock only while a laptop is authenticated, so an idle listener does not keep the CPU awake all day. Sharing the screen still uses the radio and the CPU. That is expected.

## What the app will not do

- It will not enable accessibility for you.
- It will not hide the sharing notification or the system cast icon.
- It will not read notification contents. There is no notification-listener service.
- It will not keep a screen-capture token and start sharing with no dialog.
- It will not upload the pairing token. `android:allowBackup` is false.
