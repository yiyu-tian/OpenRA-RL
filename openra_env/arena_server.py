"""Local HTTP server for side-by-side replay comparison."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable


def _compare_html(state: dict) -> str:
    state_json = json.dumps(state)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Replay Arena</title>
<style>
:root {{
  --bg: #f4efe6;
  --panel: rgba(255,255,255,0.78);
  --panel-strong: rgba(255,255,255,0.92);
  --ink: #231815;
  --muted: #7a6658;
  --accent: #a13224;
  --accent-strong: #7f2014;
  --blue: #375a7f;
  --gold: #d6a64a;
  --border: rgba(67, 40, 24, 0.12);
  --shadow: 0 20px 40px rgba(35, 24, 21, 0.12);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  min-height: 100vh;
  color: var(--ink);
  font-family: "Trebuchet MS", "Avenir Next", "Segoe UI", sans-serif;
  background:
    radial-gradient(circle at top left, rgba(214,166,74,0.28), transparent 30%),
    radial-gradient(circle at top right, rgba(55,90,127,0.16), transparent 22%),
    linear-gradient(135deg, #efe2cf 0%, #f5f1e8 48%, #d7ccb5 100%);
}}
.shell {{
  max-width: 1500px;
  margin: 0 auto;
  padding: 24px;
}}
.hero {{
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
  margin-bottom: 20px;
}}
.hero-card {{
  flex: 1;
  background: var(--panel);
  backdrop-filter: blur(18px);
  border: 1px solid var(--border);
  border-radius: 24px;
  box-shadow: var(--shadow);
  padding: 22px 24px;
}}
.eyebrow {{
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 12px;
  font-weight: 700;
}}
h1 {{
  margin: 6px 0 10px;
  font-size: clamp(2rem, 4vw, 3.6rem);
  line-height: 0.95;
  font-family: "Gill Sans", "Franklin Gothic Medium", sans-serif;
  letter-spacing: 0.03em;
}}
.subtitle {{
  color: var(--muted);
  font-size: 15px;
  max-width: 60ch;
  line-height: 1.5;
}}
.kbd-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}}
.kbd {{
  border-radius: 999px;
  padding: 8px 12px;
  background: rgba(255,255,255,0.7);
  border: 1px solid rgba(35,24,21,0.09);
  color: var(--muted);
  font-size: 13px;
}}
.arena {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}}
.lane {{
  background: var(--panel);
  backdrop-filter: blur(18px);
  border: 1px solid var(--border);
  border-radius: 24px;
  box-shadow: var(--shadow);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}}
.lane-head {{
  padding: 18px 18px 10px;
  border-bottom: 1px solid rgba(35,24,21,0.08);
}}
.lane-title {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}}
.lane-badge {{
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: 800;
  font-size: 18px;
}}
.lane-badge.left {{ background: linear-gradient(135deg, var(--accent), #d75736); }}
.lane-badge.right {{ background: linear-gradient(135deg, var(--blue), #4b8bc7); }}
.lane-name {{
  flex: 1;
  min-width: 0;
}}
.lane-name h2 {{
  margin: 0;
  font-size: 24px;
  line-height: 1.05;
}}
.lane-name p {{
  margin: 4px 0 0;
  color: var(--muted);
  font-size: 13px;
}}
.chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}}
.chip {{
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(255,255,255,0.72);
  border: 1px solid rgba(35,24,21,0.1);
  font-size: 12px;
  color: var(--muted);
}}
.viewer {{
  position: relative;
  aspect-ratio: 4 / 3;
  background: #130e0c;
}}
.viewer iframe {{
  width: 100%;
  height: 100%;
  border: 0;
  background: #130e0c;
}}
.controls {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 16px 18px 20px;
}}
.vote {{
  appearance: none;
  border: 0;
  border-radius: 18px;
  padding: 16px 18px;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
}}
.vote:hover {{
  transform: translateY(-1px);
  box-shadow: 0 14px 28px rgba(35,24,21,0.16);
}}
.vote-left {{
  background: linear-gradient(135deg, var(--accent), var(--accent-strong));
  color: white;
}}
.vote-right {{
  background: linear-gradient(135deg, var(--blue), #27415b);
  color: white;
}}
.footer {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-top: 18px;
  padding: 18px 22px;
  border-radius: 22px;
  background: var(--panel-strong);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
}}
.neutral {{
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}}
.ghost {{
  appearance: none;
  border: 1px solid rgba(35,24,21,0.12);
  background: rgba(255,255,255,0.74);
  color: var(--ink);
  border-radius: 14px;
  padding: 12px 14px;
  font-size: 14px;
  cursor: pointer;
}}
.status {{
  color: var(--muted);
  font-size: 14px;
}}
.toast {{
  position: fixed;
  right: 18px;
  bottom: 18px;
  max-width: 320px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(35,24,21,0.95);
  color: white;
  box-shadow: 0 18px 40px rgba(35,24,21,0.28);
  opacity: 0;
  transform: translateY(10px);
  pointer-events: none;
  transition: opacity .18s ease, transform .18s ease;
}}
.toast.show {{
  opacity: 1;
  transform: translateY(0);
}}
@media (max-width: 980px) {{
  .hero {{
    flex-direction: column;
  }}
  .arena {{
    grid-template-columns: 1fr;
  }}
  .controls {{
    grid-template-columns: 1fr;
  }}
  .footer {{
    flex-direction: column;
    align-items: stretch;
  }}
}}
</style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="hero-card">
        <div class="eyebrow">Replay Arena</div>
        <h1>Pick the better trajectory.</h1>
        <div class="subtitle">
          Watch both replays side by side, then record the preferred run. The choice is saved locally as JSON for downstream training or analysis.
        </div>
        <div class="kbd-row">
          <div class="kbd">1 = prefer left</div>
          <div class="kbd">2 = prefer right</div>
          <div class="kbd">S = skip / tie</div>
        </div>
      </div>
      <div class="hero-card">
        <div class="eyebrow">Session</div>
        <div class="subtitle" id="sessionMeta">Local comparison for two saved runs.</div>
      </div>
    </section>

    <section class="arena" id="arena"></section>

    <section class="footer">
      <div class="neutral">
        <button class="ghost" data-action="skip">Skip / Tie</button>
        <button class="ghost" data-action="refresh">Refresh viewers</button>
      </div>
      <div class="status" id="statusLine">Ready for evaluation.</div>
    </section>
  </div>

  <div class="toast" id="toast"></div>

<script>
const STATE = {state_json};
const arena = document.getElementById('arena');
const statusLine = document.getElementById('statusLine');
const toast = document.getElementById('toast');
document.getElementById('sessionMeta').textContent = `Comparing ${STATE.left.run_id} vs ${STATE.right.run_id}`;

function chip(text) {{
  return `<span class="chip">${{text || 'unknown'}}</span>`;
}}

function lane(entry) {{
  const iframeUrl = `http://127.0.0.1:${{entry.port}}/vnc.html?autoconnect=1&resize=scale&quality=8&compression=4`;
  const meta = entry.metadata || {{}};
  return `
    <article class="lane">
      <div class="lane-head">
        <div class="lane-title">
          <div class="lane-badge ${{entry.slot}}">${{entry.slot === 'left' ? 'A' : 'B'}}</div>
          <div class="lane-name">
            <h2>${{entry.label}}</h2>
            <p>${{entry.run_id}}</p>
          </div>
        </div>
        <div class="chips">
          ${{chip(meta.model || 'model unknown')}}
          ${{chip(meta.result || 'result unknown')}}
          ${{chip(meta.ticks ? `${{meta.ticks}} ticks` : 'ticks unknown')}}
          ${{chip(meta.map || 'map unknown')}}
          ${{chip(meta.opponent || 'opponent unknown')}}
        </div>
      </div>
      <div class="viewer">
        <iframe title="${{entry.slot}} replay" src="${{iframeUrl}}"></iframe>
      </div>
      <div class="controls">
        <button class="vote ${{entry.slot === 'left' ? 'vote-left' : 'vote-right'}}" data-vote="${{entry.slot}}">
          Prefer ${{entry.slot === 'left' ? 'A' : 'B'}}
        </button>
        <button class="ghost" onclick="window.open('${{iframeUrl}}', '_blank')">Open replay in new tab</button>
      </div>
    </article>
  `;
}}

arena.innerHTML = lane(STATE.left) + lane(STATE.right);

function flash(message, persist = false) {{
  toast.textContent = message;
  toast.classList.add('show');
  if (!persist) {{
    window.clearTimeout(window.__toastTimer);
    window.__toastTimer = window.setTimeout(() => toast.classList.remove('show'), 2800);
  }}
}}

async function savePreference(action) {{
  const body = {{ preferred_side: action }};
  const response = await fetch('/api/preferences', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json' }},
    body: JSON.stringify(body),
  }});
  const data = await response.json();
  if (!response.ok) {{
    statusLine.textContent = data.error || 'Failed to save preference.';
    flash(statusLine.textContent);
    return;
  }}
  statusLine.textContent = `Saved: ${{data.path}}`;
  flash(`Preference saved to ${{data.path}}`, true);
}}

document.addEventListener('click', (event) => {{
  const vote = event.target.getAttribute('data-vote');
  if (vote) {{
    savePreference(vote);
    return;
  }}
  const action = event.target.getAttribute('data-action');
  if (action === 'skip') {{
    savePreference('skip');
  }} else if (action === 'refresh') {{
    document.querySelectorAll('iframe').forEach((frame) => {{
      frame.src = frame.src;
    }});
    statusLine.textContent = 'Replay viewers refreshed.';
  }}
}});

document.addEventListener('keydown', (event) => {{
  if (event.key === '1') savePreference('left');
  if (event.key === '2') savePreference('right');
  if (event.key.toLowerCase() === 's') savePreference('skip');
}});
</script>
</body>
</html>"""


@dataclass
class ArenaServer:
    """Background HTTP server that hosts the compare page."""

    httpd: ThreadingHTTPServer
    thread: threading.Thread
    url: str

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def start_arena_server(
    *,
    host: str,
    port: int,
    left: dict,
    right: dict,
    save_preference: Callable[[str], str],
) -> ArenaServer:
    """Start the lightweight replay comparison server."""
    state = {"left": left, "right": right}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send(self, *, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                body = _compare_html(state).encode("utf-8")
                self._send(status=HTTPStatus.OK, body=body, content_type="text/html; charset=utf-8")
                return
            if self.path == "/api/state":
                body = json.dumps(state).encode("utf-8")
                self._send(status=HTTPStatus.OK, body=body, content_type="application/json")
                return
            self._send(
                status=HTTPStatus.NOT_FOUND,
                body=b'{"error":"not found"}',
                content_type="application/json",
            )

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/preferences":
                self._send(
                    status=HTTPStatus.NOT_FOUND,
                    body=b'{"error":"not found"}',
                    content_type="application/json",
                )
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                self._send(
                    status=HTTPStatus.BAD_REQUEST,
                    body=b'{"error":"invalid json"}',
                    content_type="application/json",
                )
                return

            preferred_side = payload.get("preferred_side", "")
            if preferred_side not in {"left", "right", "skip"}:
                self._send(
                    status=HTTPStatus.BAD_REQUEST,
                    body=b'{"error":"preferred_side must be left/right/skip"}',
                    content_type="application/json",
                )
                return

            saved_path = save_preference(preferred_side)
            body = json.dumps({"ok": True, "path": saved_path}).encode("utf-8")
            self._send(status=HTTPStatus.OK, body=body, content_type="application/json")

    httpd = ThreadingHTTPServer((host, port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return ArenaServer(httpd=httpd, thread=thread, url=f"http://{host}:{port}")
