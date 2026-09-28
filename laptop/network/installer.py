"""Let the phone download the app from the laptop over Wi-Fi.

WhatsApp's installer rejects this APK. A normal browser download on the same
Wi-Fi does not. Nothing here uses the internet.
"""

from __future__ import annotations

import logging
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from laptop.network.addresses import is_allowed_host

log = logging.getLogger(__name__)

INSTALL_PORT = 8088


def local_ipv4() -> str | None:
    """The laptop address the phone can type into Chrome."""
    found: list[str] = []
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 9))
        found.append(probe.getsockname()[0])
    except OSError:
        pass
    finally:
        probe.close()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    for host in found:
        if host.startswith("127."):
            continue
        if is_allowed_host(host) and ":" not in host:
            return host
    return None


def _page(url: str, ready: bool) -> bytes:
    if ready:
        body = """
        <p>Tap the button. When the file finishes, open it.</p>
        <a href="/PhoneRemote.apk">Download Phone Remote</a>
        <h2>If Google Play Protect says the app is blocked</h2>
        <ol>
          <li>Tap OK.</li>
          <li>Open the Play Store.</li>
          <li>Tap your profile picture, then Play Protect.</li>
          <li>Tap the gear icon.</li>
          <li>Turn off Scan apps with Play Protect.</li>
          <li>Open the download again and tap Install.</li>
          <li>Turn Scan apps with Play Protect back on.</li>
        </ol>
        <p class="note">Play Protect blocks this because the app can show your screen on the laptop and send taps. That is the feature you are installing. Turn the scan back on after it is installed.</p>
        """
    else:
        body = "<p>The install file is missing on the laptop.</p>"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phone Remote</title>
<style>
  body {{ font-family: sans-serif; background: #f4f0e8; color: #1c1917; margin: 0; padding: 28px 20px; }}
  h1 {{ font-size: 28px; margin: 0 0 8px; }}
  h2 {{ font-size: 20px; margin: 28px 0 8px; }}
  p, li {{ font-size: 18px; line-height: 1.4; }}
  ol {{ padding-left: 22px; }}
  a {{ display: block; text-align: center; background: #0f6e6e; color: white; text-decoration: none;
       font-size: 20px; font-weight: 700; padding: 16px; border-radius: 12px; margin-top: 20px; }}
  .note {{ color: #44403c; font-size: 16px; }}
</style>
</head>
<body>
  <h1>Install Phone Remote</h1>
  {body}
  <p class="note">{url}</p>
</body>
</html>
"""
    return html.encode("utf-8")


class InstallerServer:
    def __init__(self, apk_path: Path, port: int = INSTALL_PORT):
        self.apk_path = apk_path
        self.port = port
        self.url = ""
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        ip = local_ipv4()
        if ip is None:
            log.warning("No Wi-Fi address found for the phone download page")
            return ""
        handler = self._handler_type()
        last_error: OSError | None = None
        for port in range(self.port, self.port + 10):
            try:
                self._httpd = ThreadingHTTPServer(("0.0.0.0", port), handler)
            except OSError as exc:
                last_error = exc
                continue
            self.port = port
            break
        if self._httpd is None:
            log.warning("Could not open the install page: %s", last_error)
            self.url = f"http://{ip}:{self.port}"
            return self.url
        self.url = f"http://{ip}:{self.port}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="phone-install", daemon=True)
        self._thread.start()
        log.info("Phone app download page at %s", self.url)
        return self.url

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    def _handler_type(self):
        apk_path = self.apk_path
        page_url = lambda: self.url

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                path = self.path.split("?", 1)[0]
                if path in ("/PhoneRemote.apk", "/phone-remote.apk"):
                    self._send_apk()
                    return
                payload = _page(page_url(), apk_path.is_file())
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def _send_apk(self) -> None:
                if not apk_path.is_file():
                    self.send_error(404, "Install file missing")
                    return
                data = apk_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.android.package-archive")
                self.send_header("Content-Disposition", 'attachment; filename="PhoneRemote.apk"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, fmt: str, *args) -> None:
                log.info("Install page: " + fmt, *args)

        return Handler
