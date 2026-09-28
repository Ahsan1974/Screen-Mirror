# Phone Remote protocol

Version 1. The phone is the WebSocket server. The laptop is the client.
All traffic is `ws://` on the local network. There is no TLS terminator and no cloud broker.

The phone rejects a client whose source address is not private, link-local, or loopback.
Loopback exists so the laptop tests can run on one computer. It is not reachable from the internet.

## Channels

One WebSocket carries both kinds of message:

- Text frames are UTF-8 JSON control messages.
- Binary frames are screen JPEGs or file chunks. They are never base64.

The first byte of a binary frame is the type.

## Pairing

1. Laptop sends `hello`. If it already trusts this phone, `token` is included.
2. Phone replies `auth_ok` when the token matches the one it stored.
3. Otherwise the phone replies `auth_required`.
4. Laptop shows a 6-digit code and sends `pair_begin`. The code is not in that message.
5. You type the code on the phone. The phone sends `pair_submit`.
6. Laptop checks the code. On success it stores a random token and sends `pair_ok`.
7. Five wrong codes close the socket.

The token is a random URL-safe string. It is not a JWT. It is stored in
`data/paired_devices.json` on the laptop and in the phone app's private preferences.
Reinstalling either app forgets the pair.

## Control messages

`hello`

```json
{"type":"hello","protocol":1,"laptop_id":"...","laptop_name":"My PC","token":"optional"}
```

`auth_ok`

```json
{"type":"auth_ok","phone_id":"...","phone_name":"My Phone","screen_width":1080,"screen_height":2400}
```

`auth_required`

```json
{"type":"auth_required","phone_id":"...","phone_name":"My Phone"}
```

`pair_begin`

```json
{"type":"pair_begin","laptop_name":"My PC","phone_id":"...","phone_name":"My Phone"}
```

`pair_submit`

```json
{"type":"pair_submit","code":"839421","phone_id":"...","phone_name":"My Phone"}
```

`pair_ok` includes the new token. `pair_fail` has no token.

`ping` / `pong` echo a laptop monotonic timestamp so the laptop can show round-trip latency.

```json
{"type":"ping","t":123456}
{"type":"pong","t":123456}
```

`stream_start` is the laptop's capture budget. The phone keeps its aspect ratio inside the box.

```json
{"type":"stream_start","max_width":1280,"max_height":1280,"fps":15,"quality":60}
```

`stream_state` says whether capture is running.

```json
{"type":"stream_state","on":true,"screen_width":1080,"screen_height":2400}
```

`status` is sent about once a second while a laptop is authenticated.

```json
{"type":"status","sharing":true,"accessibility":true,"fps":15,"screen_width":1080,"screen_height":2400}
```

### Pointer

A click is `down` then `up`. A drag is `down`, one or more `move`, then `up`.
Coordinates are real screen pixels, not the scaled JPEG.

```json
{"type":"mouse","action":"down","x":420,"y":650,"button":"left"}
```

`action` is `down`, `move`, or `up`. `button` is `left` or `right`.
Right-click with no drag becomes a long press on the phone.

### Keyboard

```json
{"type":"key","key":"ENTER"}
```

`key` is one character (`a`, `A`, `7`) or one of:

`ENTER`, `BACKSPACE`, `DELETE`, `SPACE`, `ESCAPE`, `LEFT`, `RIGHT`, `UP`, `DOWN`.

### Navigation

```json
{"type":"navigation","action":"BACK"}
```

`action` is `BACK`, `HOME`, or `RECENTS`.

### Files

```json
{"type":"file_start","id":"11111111-1111-1111-1111-111111111111","name":"photo.jpg","size":5242880,"sha256":"..."}
```

The receiver answers `file_accept` or `file_reject`. Bytes follow as binary chunks.
The receiver answers `file_done` or `file_error`.

`id` is a 36-character UUID. `sha256` is lowercase hex. Only one transfer runs at a time.
The phone pauses screen frames during a transfer so the socket is not jammed.

### Clipboard

```json
{"type":"clipboard_push","text":"Hello"}
{"type":"clipboard_pull"}
{"type":"clipboard_data","text":"Hello","source":"phone"}
```

Text is capped at 256000 characters. The laptop log records the length, not the text.

### Errors

```json
{"type":"error","code":"projection_required","message":"Screen capture permission is required.\n\nOpen the Android application and allow screen capture."}
```

Codes used by the phone:

| Code | Meaning |
| --- | --- |
| `projection_required` | Screen sharing has not been started on the phone |
| `accessibility_disabled` | The accessibility service is off, so touch and keys cannot be injected |
| `input_failed` | The focused app does not expose an editable field |
| `key_unsupported` | The key is outside the small set above |
| `clipboard_unavailable` | Android blocked a background clipboard read |
| `protocol` | The two apps are not on protocol version 1 |

## Binary layouts

Both sides use big-endian integers. `laptop/network/protocol.py` and
`android/.../net/Protocol.kt` must stay in lockstep. The Python tests round-trip the headers.

### JPEG frame, type 1, 25-byte header

| Offset | Type | Field |
| --- | --- | --- |
| 0 | uint8 | 1 |
| 1 | uint32 | capture width |
| 5 | uint32 | capture height |
| 9 | uint32 | screen width |
| 13 | uint32 | screen height |
| 17 | uint64 | timestamp, unix milliseconds |
| 25 | bytes | JPEG, starting with `FF D8` |

Capture size is the JPEG. Screen size is the phone's real pixels, used to map the mouse.

### File chunk, type 2, 42-byte header

| Offset | Type | Field |
| --- | --- | --- |
| 0 | uint8 | 2 |
| 1 | 36 bytes | ASCII UUID |
| 37 | uint32 | sequence, starting at 0 |
| 41 | uint8 | flags, bit 0 means this is the last chunk |
| 42 | bytes | payload, usually 48 KiB |

Chunks must arrive in order. The receiver deletes the partial file if the size or SHA-256 does not match.
