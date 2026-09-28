const WS_PORT = 8765;
const WEB_PORT = 8080;

const $ = (id) => document.getElementById(id);
const portal = $("portal");
const viewer = $("viewer");
const canvas = $("screen");
const ctx = canvas.getContext("2d");
const statusEl = $("status");

let socket = null;
let authed = false;
let reconnect = true;
let phoneHost = "";
let screenW = 1080;
let screenH = 2400;
let frameSeq = 0;
let pairingCode = "";
let laptopId = localStorage.getItem("sm-laptop-id") || crypto.randomUUID();
localStorage.setItem("sm-laptop-id", laptopId);
let laptopName = localStorage.getItem("sm-laptop-name") || "Office laptop";
let token = "";
let wsPort = WS_PORT;
let retryTimer = 0;
let fpsMarks = [];
let dragButton = "";
let lastMove = 0;
let fileBusy = false;

function privateHost(host) {
  return /^(10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|127\.\d+\.\d+\.\d+)$/.test(host);
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("sm-theme", theme);
  $("theme").textContent = theme === "dark" ? "Light" : "Dark";
}

function initTheme() {
  const saved = localStorage.getItem("sm-theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (prefersDark ? "dark" : "light"));
  $("theme").addEventListener("click", () => {
    applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

function showPortal() {
  portal.hidden = false;
  viewer.hidden = true;
  $("phone-ip").value = localStorage.getItem("sm-phone-ip") || "";
  $("laptop-name").value = laptopName;
}

function showViewer() {
  portal.hidden = true;
  viewer.hidden = false;
}

function setStatus(text) {
  statusEl.textContent = text;
}

function code6() {
  const bytes = new Uint32Array(1);
  crypto.getRandomValues(bytes);
  return String(100000 + (bytes[0] % 900000));
}

function codesMatch(expected, given) {
  if (expected.length !== given.length) return false;
  let diff = 0;
  for (let i = 0; i < expected.length; i += 1) diff |= expected.charCodeAt(i) ^ given.charCodeAt(i);
  return diff === 0;
}

function tokenFor(host) {
  return localStorage.getItem(`sm-token:${host}`) || "";
}

function remember(host, phoneId, value) {
  localStorage.setItem(`sm-token:${host}`, value);
  localStorage.setItem("sm-phone-id", phoneId);
  token = value;
}

function send(message) {
  if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message));
}

function connect(host) {
  clearTimeout(retryTimer);
  const previous = socket;
  socket = null;
  if (previous) {
    previous.onclose = null;
    previous.close();
  }
  phoneHost = host;
  token = tokenFor(host);
  setStatus("Connecting…");
  const ws = new WebSocket(`ws://${host}:${wsPort}`);
  ws.binaryType = "arraybuffer";
  socket = ws;
  ws.onopen = () => {
    const hello = { type: "hello", protocol: 1, laptop_id: laptopId, laptop_name: laptopName };
    if (token) hello.token = token;
    send(hello);
  };
  ws.onmessage = (event) => {
    if (typeof event.data === "string") onText(event.data);
    else onBinary(event.data);
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    authed = false;
    $("pair").hidden = true;
    if (reconnect && privateHost(host)) {
      setStatus("Connection lost. Attempting to reconnect…");
      retryTimer = setTimeout(() => connect(host), 2000);
    } else {
      setStatus("Disconnected");
    }
  };
  ws.onerror = () => setStatus("Cannot reach the phone. Check the IP and that Phone Remote is open.");
}

function onText(raw) {
  let message;
  try { message = JSON.parse(raw); } catch { return; }
  const type = message.type;
  if (type === "auth_required") beginPair(message);
  else if (type === "auth_ok") markAuthed(message);
  else if (type === "pair_submit") onPairSubmit(message);
  else if (type === "pong" && typeof message.t === "number") {
    const ms = Math.round(performance.now() - message.t);
    if (ms >= 0 && ms < 60000) noteLatency(ms);
  } else if (type === "stream_state" || type === "status") onStatus(message);
  else if (type === "error") setStatus(message.message || "The phone reported an error.");
  else if (type === "clipboard_data") {
    $("prompt").value = message.text || "";
    navigator.clipboard?.writeText(message.text || "").catch(() => {});
    setStatus("Copied from the phone");
  } else if (type === "file_start") onFileOffer(message);
  else if (type === "file_accept" || type === "file_reject" || type === "file_done" || type === "file_error") {
    window.dispatchEvent(new CustomEvent("sm-file", { detail: message }));
  }
}

function beginPair(message) {
  if (!pairingCode) pairingCode = code6();
  $("pair-code").textContent = pairingCode;
  $("pair").hidden = false;
  send({
    type: "pair_begin",
    laptop_name: laptopName,
    phone_id: message.phone_id || "",
    phone_name: message.phone_name || "",
  });
}

function onPairSubmit(message) {
  const given = String(message.code || "").trim();
  if (!pairingCode || !codesMatch(pairingCode, given) || !message.phone_id) {
    send({ type: "pair_fail" });
    setStatus("Pairing failed. Please try again.");
    return;
  }
  const next = crypto.randomUUID() + crypto.randomUUID();
  remember(phoneHost, message.phone_id, next);
  send({ type: "pair_ok", token: next, laptop_id: laptopId, laptop_name: laptopName });
  markAuthed(message);
}

function markAuthed(message) {
  authed = true;
  pairingCode = "";
  $("pair").hidden = true;
  $("device-line").textContent = message.phone_name || "My Phone";
  if (message.screen_width) screenW = message.screen_width;
  if (message.screen_height) screenH = message.screen_height;
  fitDevice();
  setStatus("Connected");
  send({ type: "stream_start", max_width: 1280, max_height: 1280, fps: 15, quality: 80 });
  startPing();
}

let pingTimer = 0;
function startPing() {
  clearInterval(pingTimer);
    pingTimer = setInterval(() => {
    if (authed) send({ type: "ping", t: Math.round(performance.now()) });
  }, 1000);
}

function noteLatency(ms) {
  const now = performance.now();
  fpsMarks = fpsMarks.filter((t) => now - t < 1000);
  $("meta").textContent = `Wi-Fi · ${ms} ms · ${fpsMarks.length} fps`;
}

function onStatus(message) {
  if (message.message) setStatus(message.message);
  if (message.screen_width) screenW = message.screen_width;
  if (message.screen_height) screenH = message.screen_height;
  fitDevice();
  const sharing = message.sharing || message.on;
  if (message.accessibility === false) {
    setStatus("Turn on Phone Remote in Accessibility to tap and type.");
  } else if (sharing) {
    setStatus("Screen on");
  }
}

function fitDevice() {
  const ratio = screenW / screenH;
  const height = canvas.parentElement.clientHeight || 700;
  canvas.style.height = `${height}px`;
  canvas.style.width = `${Math.round(height * ratio)}px`;
}

function onBinary(buffer) {
  const view = new DataView(buffer);
  if (buffer.byteLength < 25 || view.getUint8(0) !== 1) return;
  screenW = view.getUint32(9, false) || screenW;
  screenH = view.getUint32(13, false) || screenH;
  const seq = ++frameSeq;
  const jpeg = new Blob([buffer.slice(25)], { type: "image/jpeg" });
  const url = URL.createObjectURL(jpeg);
  const image = new Image();
  image.onload = () => {
    URL.revokeObjectURL(url);
    if (seq !== frameSeq) return;
    if (canvas.width !== image.naturalWidth || canvas.height !== image.naturalHeight) {
      canvas.width = image.naturalWidth;
      canvas.height = image.naturalHeight;
    }
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(image, 0, 0);
    $("placeholder").hidden = true;
    fitDevice();
  };
  image.onerror = () => URL.revokeObjectURL(url);
  image.src = url;
  fpsMarks.push(performance.now());
}

function pointer(event, action, button) {
  if (!authed) return;
  const rect = canvas.getBoundingClientRect();
  if (rect.width < 2 || rect.height < 2) return;
  const x = Math.round((event.clientX - rect.left) / rect.width * screenW);
  const y = Math.round((event.clientY - rect.top) / rect.height * screenH);
  if (x < 0 || y < 0 || x >= screenW || y >= screenH) return;
  send({ type: "mouse", action, x, y, button });
}

canvas.addEventListener("pointerdown", (event) => {
  canvas.setPointerCapture(event.pointerId);
  canvas.focus?.();
  dragButton = event.button === 2 ? "right" : "left";
  pointer(event, "down", dragButton);
});
canvas.addEventListener("pointermove", (event) => {
  if (!dragButton || dragButton === "right") return;
  const now = performance.now();
  if (now - lastMove < 30) return;
  lastMove = now;
  pointer(event, "move", "left");
});
canvas.addEventListener("pointerup", (event) => {
  const button = event.button === 2 ? "right" : "left";
  pointer(event, "up", button);
  dragButton = "";
});
canvas.addEventListener("contextmenu", (event) => event.preventDefault());

function sendPrompt() {
  const text = $("prompt").value.slice(0, 20000);
  if (!text.trim()) return;
  send({ type: "text_insert", text });
  setStatus("Sending into the phone…");
}

window.addEventListener("keydown", async (event) => {
  if (viewer.hidden) return;
  if (event.target.matches("input, textarea")) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      sendPrompt();
    }
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
    event.preventDefault();
    let text = "";
    try { text = await navigator.clipboard.readText(); } catch { text = $("prompt").value; }
    if (text) send({ type: "text_insert", text: text.slice(0, 20000) });
    return;
  }
  if (event.ctrlKey || event.altKey || event.metaKey) return;
  const key = specialKey(event);
  if (!key) return;
  send({ type: "key", key });
  event.preventDefault();
});

function specialKey(event) {
  const map = {
    Enter: event.shiftKey ? "NEWLINE" : "ENTER", Backspace: "BACKSPACE", Delete: "DELETE", Escape: "ESCAPE",
    ArrowLeft: "LEFT", ArrowRight: "RIGHT", ArrowUp: "UP", ArrowDown: "DOWN", " ": "SPACE",
  };
  if (map[event.key]) return map[event.key];
  if (event.key.length === 1) return event.key;
  return "";
}

document.querySelectorAll("[data-nav]").forEach((button) => {
  button.addEventListener("click", () => send({ type: "navigation", action: button.dataset.nav }));
});

$("send-prompt").addEventListener("click", sendPrompt);
$("copy-chat").addEventListener("click", () => {
  send({ type: "screen_text" });
  setStatus("Reading the phone screen…");
});
$("get-clip").addEventListener("click", () => send({ type: "clipboard_pull" }));
$("disconnect").addEventListener("click", () => {
  reconnect = false;
  socket?.close();
  setStatus("Disconnected");
});

$("file").addEventListener("change", async () => {
  const file = $("file").files?.[0];
  $("file").value = "";
  if (!file || !authed || fileBusy) return;
  fileBusy = true;
  const bytes = new Uint8Array(await file.arrayBuffer());
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const sha = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
  const id = crypto.randomUUID();
  $("transfer").textContent = `Sending ${file.name}`;
  send({ type: "file_start", id, name: file.name, size: bytes.length, sha256: sha });
  const accepted = await waitFile(id, "file_accept", "file_reject");
  if (!accepted) {
    $("transfer").textContent = "The phone did not accept the file.";
    fileBusy = false;
    return;
  }
  const chunk = 48 * 1024;
  let offset = 0;
  let sequence = 0;
  while (offset < bytes.length || bytes.length === 0) {
    const piece = bytes.subarray(offset, offset + chunk);
    const last = offset + piece.length >= bytes.length;
    socket.send(packChunk(id, sequence, last, piece));
    offset += piece.length;
    sequence += 1;
    $("transfer").textContent = `${file.name} ${Math.min(100, Math.round(offset * 100 / (bytes.length || 1)))}%`;
    if (last) break;
    await new Promise((resolve) => setTimeout(resolve, 15));
  }
  await waitFile(id, "file_done", "file_error");
  $("transfer").textContent = `Sent ${file.name}`;
  fileBusy = false;
});

function packChunk(id, sequence, last, payload) {
  const out = new Uint8Array(42 + payload.length);
  const view = new DataView(out.buffer);
  view.setUint8(0, 2);
  new TextEncoder().encodeInto(id, out.subarray(1, 37));
  view.setUint32(37, sequence, false);
  view.setUint8(41, last ? 1 : 0);
  out.set(payload, 42);
  return out;
}

function waitFile(id, okType, badType) {
  return new Promise((resolve) => {
    const onEvent = (event) => {
      const message = event.detail;
      if (message.id !== id) return;
      if (message.type === okType || message.type === badType) {
        window.removeEventListener("sm-file", onEvent);
        resolve(message.type === okType);
      }
    };
    window.addEventListener("sm-file", onEvent);
    setTimeout(() => {
      window.removeEventListener("sm-file", onEvent);
      resolve(false);
    }, 120000);
  });
}

async function onFileOffer(message) {
  const yes = window.confirm(`Receive ${message.name} from the phone?`);
  if (!yes) {
    send({ type: "file_reject", id: message.id, reason: "declined" });
    return;
  }
  send({ type: "file_accept", id: message.id });
  const parts = [];
  let next = 0;
  const done = new Promise((resolve) => {
    const onEvent = (event) => {
      const item = event.detail;
      if (item.id !== message.id || item.type !== "file_error") return;
      window.removeEventListener("sm-file", onEvent);
      resolve(false);
    };
    window.addEventListener("sm-file", onEvent);
  });
  const received = new Promise((resolve) => {
    const original = socket.onmessage;
    socket.addEventListener("message", function onBin(event) {
      if (typeof event.data === "string") return;
      const view = new DataView(event.data);
      if (view.getUint8(0) !== 2) return;
      const id = new TextDecoder().decode(event.data.slice(1, 37));
      if (id !== message.id) return;
      const sequence = view.getUint32(37, false);
      const last = (view.getUint8(41) & 1) === 1;
      if (sequence === next) {
        parts.push(event.data.slice(42));
        next += 1;
        if (last) {
          socket.removeEventListener("message", onBin);
          resolve(true);
        }
      }
    });
    void original;
  });
  if (await Promise.race([received, done])) {
    const blob = new Blob(parts);
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = message.name || "file";
    link.click();
    send({ type: "file_done", id: message.id, name: message.name, size: message.size });
  }
}

function cleanHost(value) {
  return value.trim().replace(/^https?:\/\//i, "").split("/")[0].split(":")[0];
}

$("join").addEventListener("submit", (event) => {
  event.preventDefault();
  const host = cleanHost($("phone-ip").value);
  laptopName = $("laptop-name").value.trim().slice(0, 40) || "Office laptop";
  localStorage.setItem("sm-laptop-name", laptopName);
  if (!privateHost(host)) {
    setStatus("Enter the private Wi-Fi address shown on the phone.");
    return;
  }
  localStorage.setItem("sm-phone-ip", host);
  window.location.href = `http://${host}:${WEB_PORT}`;
});

window.addEventListener("resize", fitDevice);
initTheme();
if (privateHost(location.hostname)) {
  showViewer();
  reconnect = true;
  fetch("/config.json", { cache: "no-store" })
    .then((response) => (response.ok ? response.json() : null))
    .then((config) => {
      if (config && Number(config.port) > 0) wsPort = Number(config.port);
    })
    .catch(() => {})
    .finally(() => connect(location.hostname));
} else {
  showPortal();
  setStatus("Enter the phone’s Wi-Fi address");
}
