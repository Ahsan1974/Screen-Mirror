"""Message type names shared by the laptop and documented for the Android app.

The phone app is Kotlin, so it cannot import this module. The same strings live in
android/.../net/Protocol.kt. If you add a type, update both files and shared/protocol.md.
"""

PROTOCOL_VERSION = 1

HELLO = "hello"
AUTH_OK = "auth_ok"
AUTH_REQUIRED = "auth_required"
PAIR_BEGIN = "pair_begin"
PAIR_SUBMIT = "pair_submit"
PAIR_OK = "pair_ok"
PAIR_FAIL = "pair_fail"
PING = "ping"
PONG = "pong"
STREAM_START = "stream_start"
STREAM_STATE = "stream_state"
MOUSE = "mouse"
KEY = "key"
NAVIGATION = "navigation"
FILE_START = "file_start"
FILE_ACCEPT = "file_accept"
FILE_REJECT = "file_reject"
FILE_DONE = "file_done"
FILE_ERROR = "file_error"
TEXT_INSERT = "text_insert"
SCREEN_TEXT = "screen_text"
CLIPBOARD_PUSH = "clipboard_push"
CLIPBOARD_PULL = "clipboard_pull"
CLIPBOARD_DATA = "clipboard_data"
ERROR = "error"
STATUS = "status"

# First byte of a binary WebSocket frame.
BINARY_FRAME = 1
BINARY_FILE_CHUNK = 2

NAV_BACK = "BACK"
NAV_HOME = "HOME"
NAV_RECENTS = "RECENTS"

CLIPBOARD_MAX_CHARS = 256_000
FILE_CHUNK_SIZE = 48 * 1024
