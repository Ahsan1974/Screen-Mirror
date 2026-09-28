"""Map a click on the laptop window onto the phone's real screen pixels.

The window letterboxes the picture so the aspect ratio stays correct.
Touches outside the picture are ignored.
"""

from __future__ import annotations


def mouse_message(action: str, x: int, y: int, button: str = "left") -> dict:
    if action not in {"down", "move", "up"}:
        raise ValueError(f"unsupported mouse action {action}")
    if button not in {"left", "right"}:
        raise ValueError(f"unsupported mouse button {button}")
    return {"type": "mouse", "action": action, "x": int(x), "y": int(y), "button": button}


def letterbox(widget_w: float, widget_h: float, frame_w: float, frame_h: float):
    if widget_w <= 0 or widget_h <= 0 or frame_w <= 0 or frame_h <= 0:
        return None
    scale = min(widget_w / frame_w, widget_h / frame_h)
    draw_w = frame_w * scale
    draw_h = frame_h * scale
    off_x = (widget_w - draw_w) / 2
    off_y = (widget_h - draw_h) / 2
    return off_x, off_y, draw_w, draw_h, scale


def map_pointer(
    widget_w: float,
    widget_h: float,
    frame_w: float,
    frame_h: float,
    screen_w: float,
    screen_h: float,
    x: float,
    y: float,
) -> tuple[int, int] | None:
    box = letterbox(widget_w, widget_h, frame_w, frame_h)
    if box is None or screen_w <= 0 or screen_h <= 0:
        return None
    off_x, off_y, draw_w, draw_h, scale = box
    if x < off_x or y < off_y or x > off_x + draw_w or y > off_y + draw_h:
        return None
    frame_x = (x - off_x) / scale
    frame_y = (y - off_y) / scale
    screen_x = int(round(frame_x / frame_w * screen_w))
    screen_y = int(round(frame_y / frame_h * screen_h))
    screen_x = min(max(screen_x, 0), int(screen_w) - 1)
    screen_y = min(max(screen_y, 0), int(screen_h) - 1)
    return screen_x, screen_y
