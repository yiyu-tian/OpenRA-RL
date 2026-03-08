"""Arena controller and HTML renderer for local replay comparison."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class ArenaController:
    """Own arena state while the local arena app serves the UI."""

    list_runs: Callable[[], list[dict[str, Any]]]
    start_compare: Callable[[str, str, str, list[str]], dict[str, Any]]
    save_preference: Callable[[str], str]
    stop_compare: Callable[[], None]
    fair_fields: list[dict[str, str]]
    default_fair_fields: list[str]
    initial_session: Optional[dict[str, Any]] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _session: Optional[dict[str, Any]] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._session = self.initial_session

    def snapshot(self) -> dict[str, Any]:
        """Return the current UI state snapshot."""
        with self._lock:
            session = self._session
        return {
            "configured": True,
            "session": session,
            "fair_fields": self.fair_fields,
            "default_fair_fields": self.default_fair_fields,
            "runs": self.list_runs(),
        }

    def start_session(
        self,
        left_run_id: str,
        right_run_id: str,
        comparison_mode: str,
        fair_fields: list[str],
    ) -> dict[str, Any]:
        """Launch or relaunch the replay comparison session."""
        if not left_run_id or not right_run_id:
            raise ValueError("left_run_id and right_run_id are required")
        if comparison_mode not in {"fair", "ab", "manual"}:
            raise ValueError("comparison_mode must be fair, ab, or manual")
        session = self.start_compare(left_run_id, right_run_id, comparison_mode, fair_fields)
        with self._lock:
            self._session = session
        return session

    def save_vote(self, preferred_side: str) -> str:
        """Persist a saved preference for the active session."""
        if preferred_side not in {"left", "right", "skip"}:
            raise ValueError("preferred_side must be left, right, or skip")
        with self._lock:
            if self._session is None:
                raise RuntimeError("No active arena session.")
        return self.save_preference(preferred_side)

    def stop_session(self) -> None:
        """Stop both replay viewers and clear the current session."""
        self.stop_compare()
        with self._lock:
            self._session = None


def empty_arena_state() -> dict[str, Any]:
    """Return the bootstrap state when arena mode is not configured."""
    return {
        "configured": False,
        "session": None,
        "fair_fields": [],
        "default_fair_fields": [],
        "runs": [],
    }


_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Arena - Replay Pairing</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Teko:wght@400;600;700&display=swap" rel="stylesheet">
<style>
__ARENA_CSS__
</style>
</head>
<body>
<div class="scanlines"></div>
"""

_SCRIPT = """<script type="module">
__ARENA_SCRIPT__
</script>
</body>
</html>"""


def render_arena_page(state: dict[str, Any]) -> str:
    """Render the arena page HTML."""
    state_json = json.dumps(state).replace("</", "<\\/")
    html = _HEAD.replace("__ARENA_CSS__", _arena_css())
    html += _arena_body()
    html += _SCRIPT.replace("__ARENA_SCRIPT__", _arena_script(state_json))
    return html


def _arena_css() -> str:
    return """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Share Tech Mono', monospace;
  background: radial-gradient(circle at top, #2a0909 0%, #090909 56%, #030303 100%);
  color: #d1d5db;
  min-height: 100vh;
}
a { color: #d1d5db; text-decoration: none; transition: color .2s; }
a:hover { color: #fff; }
button, input { font: inherit; }
h1, h2, h3, .font-teko {
  font-family: 'Teko', sans-serif;
  letter-spacing: 1px;
  text-transform: uppercase;
}
.scanlines {
  background: linear-gradient(to bottom, rgba(255,255,255,0), rgba(255,255,255,0) 50%, rgba(0,0,0,0.18) 50%, rgba(0,0,0,0.18));
  background-size: 100% 4px;
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 50;
}
.terminal-text { color: #84cc16; text-shadow: 0 0 5px rgba(132,204,22,.45); }
.alert-text { color: #ef4444; text-shadow: 0 0 8px rgba(239,68,68,.7); }
nav {
  border-bottom: 2px solid #991b1b;
  background: rgba(0,0,0,.9);
  position: sticky;
  top: 0;
  z-index: 40;
  backdrop-filter: blur(4px);
}
.nav-inner {
  max-width: 90rem;
  margin: 0 auto;
  padding: 0 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 4rem;
}
.nav-logo { display: flex; align-items: center; gap: .6rem; }
.nav-logo svg { width: 2rem; height: 2rem; color: #dc2626; animation: spin 4s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.nav-logo span {
  font-family: 'Teko', sans-serif;
  font-size: 1.8rem;
  font-weight: 700;
  color: #fff;
  letter-spacing: .15em;
}
.nav-logo .rl { color: #dc2626; }
.nav-links { display: flex; gap: 1.5rem; align-items: center; }
.nav-links a {
  font-family: 'Teko', sans-serif;
  font-size: 1.15rem;
  letter-spacing: .1em;
  color: #9ca3af;
  text-transform: uppercase;
}
.nav-links a:hover { color: #fff; }
.nav-status {
  font-family: 'Teko', sans-serif;
  font-size: 1.05rem;
  letter-spacing: .12em;
  color: #9ca3af;
  text-transform: uppercase;
  border: 1px solid #3f3f46;
  padding: .2rem .65rem;
}
.page {
  max-width: 90rem;
  margin: 0 auto;
  padding: 2rem 1.5rem 3rem;
  display: grid;
  gap: 1.5rem;
}
.hero {
  background: linear-gradient(180deg, rgba(24,24,24,.96), rgba(10,10,10,.96));
  border: 2px solid #262626;
  border-left: 4px solid #dc2626;
  padding: 1.8rem;
  box-shadow: 0 0 36px rgba(0,0,0,.5);
}
.hero-top {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  flex-wrap: wrap;
}
.hero h1 { font-size: clamp(2.2rem, 5vw, 3.6rem); color: #fff; line-height: .95; margin-top: .4rem; }
.hero p { color: #9ca3af; line-height: 1.7; max-width: 60rem; }
.chip-row, .meta-row, .filter-row, .slot-chips, .viewer-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: .5rem;
}
.chip, .filter-pill {
  display: inline-flex;
  align-items: center;
  gap: .45rem;
  padding: .35rem .8rem;
  border: 1px solid #3f3f46;
  border-radius: 999px;
  font-size: .78rem;
  color: #d1d5db;
  background: rgba(17,17,17,.9);
}
.summary-grid, .workspace, .compare-grid {
  display: grid;
  gap: 1.5rem;
}
.summary-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.summary-card, .panel, .viewer-card {
  background: linear-gradient(180deg, rgba(18,18,18,.96), rgba(10,10,10,.96));
  border: 2px solid #262626;
  box-shadow: 0 0 28px rgba(0,0,0,.45);
}
.summary-card { padding: 1.2rem 1.25rem; }
.summary-card h2 { color: #fff; font-size: 1.5rem; margin-bottom: .4rem; }
.summary-card p { color: #9ca3af; line-height: 1.55; font-size: .88rem; }
.workspace { grid-template-columns: minmax(19rem, 24rem) minmax(0, 1fr); }
.panel { padding: 1.3rem; }
.panel h2 { font-size: 1.7rem; color: #fff; margin-bottom: .6rem; }
.panel p.hint, .status-line, .subtle {
  color: #9ca3af;
  line-height: 1.6;
  font-size: .84rem;
}
.segmented {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .75rem;
  margin: 1rem 0;
}
.segmented button, .btn-soviet, .btn-ghost, .slot-btn, .vote-btn {
  border: 2px solid #3f3f46;
  transition: all .12s ease;
  cursor: pointer;
}
.segmented button, .btn-ghost, .slot-btn {
  background: #121212;
  color: #d1d5db;
  padding: .65rem .9rem;
}
.segmented button.active {
  background: #dc2626;
  border-color: #f87171;
  color: #fff;
  box-shadow: 4px 4px 0 #000;
}
.btn-soviet {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .5rem;
  background: #dc2626;
  border-color: #f87171;
  box-shadow: 4px 4px 0 #000;
  color: #fff;
  font-family: 'Teko', sans-serif;
  font-size: 1.45rem;
  padding: .45rem 1.2rem;
  text-transform: uppercase;
}
.btn-ghost {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: .4rem;
  box-shadow: 4px 4px 0 #000;
  font-family: 'Teko', sans-serif;
  font-size: 1.25rem;
  padding: .45rem 1.05rem;
  text-transform: uppercase;
}
.btn-soviet:hover, .btn-ghost:hover, .slot-btn:hover, .vote-btn:hover, .segmented button:hover {
  transform: translate(2px, 2px);
  box-shadow: 2px 2px 0 #000;
}
.btn-ghost:disabled, .btn-soviet:disabled, .slot-btn:disabled, .vote-btn:disabled {
  opacity: .45;
  cursor: not-allowed;
  transform: none;
  box-shadow: 4px 4px 0 #000;
}
.search-input {
  width: 100%;
  background: #080808;
  color: #d1d5db;
  border: 2px solid #3f3f46;
  padding: .75rem .9rem;
  margin-bottom: .9rem;
}
.filter-row { margin-top: .65rem; }
.filter-pill { background: #0f0f0f; }
.filter-pill input { accent-color: #dc2626; }
.slot-list { display: grid; gap: 1rem; }
.slot-card {
  background: #0c0c0c;
  border: 2px solid #262626;
  border-left: 4px solid #525252;
  padding: 1rem;
}
.slot-card.left { border-left-color: #dc2626; }
.slot-card.right { border-left-color: #2563eb; }
.slot-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  margin-bottom: .75rem;
}
.slot-title { color: #fff; font-size: 1.4rem; }
.slot-empty { color: #6b7280; line-height: 1.55; font-size: .86rem; }
.slot-actions { display: grid; grid-template-columns: 1fr 1fr; gap: .75rem; margin-top: 1rem; }
.catalog-head, .compare-head {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}
.toolbar { display: flex; gap: .75rem; flex-wrap: wrap; }
.toolbar .btn-ghost, .toolbar .btn-soviet { font-size: 1.12rem; }
.run-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: 1rem;
}
.run-card {
  background: #0c0c0c;
  border: 2px solid #262626;
  padding: 1rem;
  display: grid;
  gap: .8rem;
}
.run-card.selected-left { border-color: rgba(220, 38, 38, .75); }
.run-card.selected-right { border-color: rgba(37, 99, 235, .75); }
.run-card.incompatible { opacity: .5; }
.run-card strong {
  display: block;
  color: #fff;
  font-size: 1.05rem;
  line-height: 1.35;
}
.run-card .run-id { color: #9ca3af; font-size: .74rem; }
.result-pill {
  font-size: .74rem;
  padding: .2rem .6rem;
  border-radius: 999px;
  border: 1px solid #3f3f46;
  text-transform: uppercase;
}
.result-win { color: #4ade80; border-color: rgba(74,222,128,.4); }
.result-lose { color: #f87171; border-color: rgba(248,113,113,.4); }
.result-neutral { color: #93c5fd; border-color: rgba(147,197,253,.35); }
.run-top, .viewer-top {
  display: flex;
  justify-content: space-between;
  gap: .75rem;
  align-items: flex-start;
}
.run-actions, .viewer-toolbar, .vote-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: .75rem;
}
.compare-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.viewer-card { padding: 1rem; display: grid; gap: .9rem; }
.viewer-label {
  width: 2.5rem;
  height: 2.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 2px solid #3f3f46;
  background: #0f0f0f;
  color: #fff;
  font-family: 'Teko', sans-serif;
  font-size: 1.5rem;
}
.viewer-label.left { border-color: #f87171; color: #fca5a5; }
.viewer-label.right { border-color: #60a5fa; color: #93c5fd; }
.viewer-stage {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 3;
  background: #050505;
  border: 2px solid #171717;
  overflow: hidden;
}
.viewer-stage .placeholder, .viewer-stage .viewer-message {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  text-align: center;
  padding: 1.2rem;
  color: #9ca3af;
  line-height: 1.6;
  background: linear-gradient(180deg, rgba(6,6,6,.92), rgba(12,12,12,.85));
}
.viewer-surface { width: 100%; height: 100%; }
.viewer-surface canvas {
  width: 100% !important;
  height: 100% !important;
  display: block;
}
.viewer-status {
  min-height: 2.5rem;
  color: #9ca3af;
  font-size: .82rem;
  line-height: 1.5;
}
.vote-btn {
  color: #fff;
  font-family: 'Teko', sans-serif;
  font-size: 1.5rem;
  text-transform: uppercase;
  padding: .45rem 1rem;
  box-shadow: 4px 4px 0 #000;
}
.vote-left { background: #b91c1c; border-color: #f87171; }
.vote-right { background: #1d4ed8; border-color: #93c5fd; }
.empty-state {
  border: 2px dashed #3f3f46;
  padding: 1.4rem;
  color: #9ca3af;
  line-height: 1.7;
  text-align: center;
}
.toast {
  position: fixed;
  right: 1rem;
  bottom: 1rem;
  background: rgba(5,5,5,.96);
  color: #fff;
  border: 2px solid #262626;
  padding: .85rem 1rem;
  max-width: 24rem;
  opacity: 0;
  pointer-events: none;
  transform: translateY(10px);
  transition: opacity .18s ease, transform .18s ease;
  z-index: 60;
}
.toast.show { opacity: 1; transform: translateY(0); }
footer {
  background: #000;
  border-top: 2px solid #7f1d1d;
  padding: 1.5rem;
  text-align: center;
  font-size: .8rem;
  color: #6b7280;
}
@media (max-width: 1100px) {
  .summary-grid, .workspace, .compare-grid { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .nav-links { display: none; }
  .slot-actions, .run-actions, .viewer-toolbar, .vote-row, .segmented { grid-template-columns: 1fr; }
}
"""


def _arena_body() -> str:
    return """
<nav>
  <div class="nav-inner">
    <a href="/" class="nav-logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="square" stroke-linejoin="miter">
        <circle cx="12" cy="12" r="10"></circle>
        <circle cx="12" cy="12" r="6" stroke-opacity="0.5"></circle>
        <circle cx="12" cy="12" r="2" fill="currentColor"></circle>
        <path d="M12 12l8.5-8.5"></path>
        <path d="M12 2v10H2" stroke-opacity="0.5" stroke-dasharray="2 2"></path>
      </svg>
      <span>OPENRA<span class="rl">-RL</span></span>
    </a>
    <div class="nav-status">Local Only</div>
  </div>
</nav>

<main class="page">
  <section class="hero">
    <div class="hero-top">
      <div>
        <div class="terminal-text">LOCAL PAIRING MODE</div>
        <h1 class="alert-text">Replay Arena</h1>
      </div>
      <div class="chip-row">
        <span class="chip">Chrome-ready pairing UI</span>
        <span class="chip">Fair-match filters</span>
        <span class="chip">Open A/B mode</span>
        <span class="chip">Local JSON preferences</span>
      </div>
    </div>
    <p>
      Select two saved runs, optionally constrain them to the same start state, and compare them directly in-page.
      This arena is a local evaluation workflow, separate from the hosted TRY demo, and renders both replay sessions into page-owned viewer surfaces.
    </p>
  </section>

  <section class="summary-grid">
    <article class="summary-card">
      <h2>Mode</h2>
      <p id="modeSummary">Loading arena mode...</p>
    </article>
    <article class="summary-card">
      <h2>Selection</h2>
      <p id="selectionSummary">Loading selected runs...</p>
    </article>
    <article class="summary-card">
      <h2>Session</h2>
      <p id="sessionSummary">Loading replay session...</p>
    </article>
  </section>

  <section class="workspace">
    <aside class="panel">
      <h2>Pairing Controls</h2>
      <p class="hint">
        Fair Comparison enforces exact matches on the chosen start-state fields. Open A/B removes those constraints for free-form evaluation.
      </p>
      <div class="segmented">
        <button type="button" id="modeFair">Fair Comparison</button>
        <button type="button" id="modeAb">Open A/B</button>
      </div>
      <input id="searchInput" class="search-input" type="search" placeholder="Search by run id, model, map, result..." />
      <div class="subtle">Fair-match fields</div>
      <div class="filter-row" id="fairFieldGrid"></div>
      <div class="subtle" style="margin-top:1rem" id="configStatus"></div>
    </aside>

    <section class="panel">
      <div class="catalog-head">
        <div>
          <h2>Run Catalog</h2>
          <div class="status-line" id="catalogStats"></div>
        </div>
        <div class="toolbar">
          <button type="button" class="btn-ghost" id="refreshCatalogBtn">Refresh Catalog</button>
        </div>
      </div>
      <div class="run-grid" id="runGrid"></div>
    </section>
  </section>

  <section class="workspace">
    <aside class="panel">
      <h2>Selected Runs</h2>
      <div class="slot-list">
        <div class="slot-card left">
          <div class="slot-top">
            <div class="slot-title">Slot A</div>
            <button type="button" class="btn-ghost" data-clear-slot="left">Clear</button>
          </div>
          <div id="slotLeft"></div>
        </div>
        <div class="slot-card right">
          <div class="slot-top">
            <div class="slot-title">Slot B</div>
            <button type="button" class="btn-ghost" data-clear-slot="right">Clear</button>
          </div>
          <div id="slotRight"></div>
        </div>
      </div>
      <div class="slot-actions">
        <button type="button" class="btn-soviet" id="launchBtn">Launch Comparison</button>
        <button type="button" class="btn-ghost" id="resetSelectionBtn">Reset Selection</button>
      </div>
      <div class="status-line" style="margin-top:1rem" id="compatHint"></div>
    </aside>

    <section class="panel">
      <div class="compare-head">
        <div>
          <h2>Live Comparison</h2>
          <div class="status-line" id="compareMeta"></div>
        </div>
        <div class="toolbar">
          <button type="button" class="btn-ghost" id="refreshViewersBtn">Reconnect Viewers</button>
          <button type="button" class="btn-ghost" id="skipBtn">Skip / Tie</button>
          <button type="button" class="btn-ghost" id="stopSessionBtn">Stop Viewers</button>
        </div>
      </div>
      <div id="compareBody"></div>
      <div style="display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap;margin-top:1rem;">
        <div class="status-line" id="statusLine">Ready.</div>
        <div class="status-line">Keyboard: 1 = prefer A, 2 = prefer B, S = skip / tie</div>
      </div>
    </section>
  </section>
</main>

<footer>&copy; 2026 OpenRA-RL Contributors - <a href="/">Home</a> - <a href="/try">Try</a></footer>
<div class="toast" id="toast"></div>
"""


def _arena_script(state_json: str) -> str:
    return """
import noVNC from 'https://cdn.jsdelivr.net/npm/@novnc/novnc@1.5.0/+esm';

const RFB = noVNC.default || noVNC;

const BOOTSTRAP = __STATE__;
const state = {
  configured: Boolean(BOOTSTRAP.configured),
  runs: Array.isArray(BOOTSTRAP.runs) ? BOOTSTRAP.runs : [],
  fairFields: Array.isArray(BOOTSTRAP.fair_fields) ? BOOTSTRAP.fair_fields : [],
  defaultFairFields: Array.isArray(BOOTSTRAP.default_fair_fields) ? BOOTSTRAP.default_fair_fields : [],
  selection: {
    left: BOOTSTRAP.session ? BOOTSTRAP.session.left : null,
    right: BOOTSTRAP.session ? BOOTSTRAP.session.right : null,
  },
  session: BOOTSTRAP.session || null,
  mode: BOOTSTRAP.session && BOOTSTRAP.session.comparison_mode === 'ab' ? 'ab' : 'fair',
  fairSelection: new Set(
    BOOTSTRAP.session && Array.isArray(BOOTSTRAP.session.fair_fields) && BOOTSTRAP.session.fair_fields.length
      ? BOOTSTRAP.session.fair_fields
      : (BOOTSTRAP.default_fair_fields || [])
  ),
  search: '',
  composers: { left: null, right: null },
};

const modeFairBtn = document.getElementById('modeFair');
const modeAbBtn = document.getElementById('modeAb');
const fairFieldGrid = document.getElementById('fairFieldGrid');
const slotLeft = document.getElementById('slotLeft');
const slotRight = document.getElementById('slotRight');
const runGrid = document.getElementById('runGrid');
const compareBody = document.getElementById('compareBody');
const compareMeta = document.getElementById('compareMeta');
const statusLine = document.getElementById('statusLine');
const toast = document.getElementById('toast');
const configStatus = document.getElementById('configStatus');

class ReplayComposer {
  constructor(slot, root, statusNode) {
    this.slot = slot;
    this.root = root;
    this.statusNode = statusNode;
    this.rfb = null;
    this.signature = '';
  }

  disconnect() {
    this.signature = '';
    if (this.rfb) {
      try {
        this.rfb.disconnect();
      } catch (error) {
      }
      this.rfb = null;
    }
    if (this.root) {
      this.root.innerHTML = '<div class="placeholder">Launch a comparison to load this replay canvas.</div>';
    }
    this.setStatus('Idle.');
  }

  setStatus(message) {
    if (this.statusNode) {
      this.statusNode.textContent = message;
    }
  }

  connect(entry, force) {
    if (!entry || !entry.port) {
      this.disconnect();
      return;
    }
    const signature = entry.run_id + ':' + entry.port;
    if (!force && this.rfb && this.signature === signature) {
      return;
    }
    this.disconnect();
    this.signature = signature;

    const surface = document.createElement('div');
    surface.className = 'viewer-surface';
    this.root.innerHTML = '';
    this.root.appendChild(surface);

    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const wsUrl = scheme + '://127.0.0.1:' + entry.port + '/websockify';
    this.setStatus('Connecting to replay viewer on :' + entry.port + '...');

    try {
      const rfb = new RFB(surface, wsUrl, { shared: true });
      this.rfb = rfb;
      rfb.scaleViewport = true;
      rfb.resizeSession = false;
      rfb.clipViewport = false;
      rfb.viewOnly = true;
      rfb.background = '#050505';
      rfb.qualityLevel = 8;
      rfb.compressionLevel = 4;
      rfb.addEventListener('connect', () => {
        this.setStatus('Live on :' + entry.port);
      });
      rfb.addEventListener('disconnect', (event) => {
        const clean = Boolean(event.detail && event.detail.clean);
        this.setStatus(clean ? 'Viewer disconnected cleanly.' : 'Viewer connection lost.');
      });
      rfb.addEventListener('credentialsrequired', () => {
        try {
          rfb.sendCredentials({ password: '' });
        } catch (error) {
        }
      });
      rfb.addEventListener('securityfailure', () => {
        this.setStatus('Viewer security handshake failed.');
      });
    } catch (error) {
      this.setStatus('Failed to attach viewer: ' + error.message);
      this.root.innerHTML = '<div class="viewer-message">Could not attach the replay canvas. Use Reconnect Viewers after the containers are ready.</div>';
    }
  }
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function normalize(value) {
  if (value === null || value === undefined) {
    return '';
  }
  return String(value).trim().toLowerCase();
}

function chip(text) {
  return '<span class="chip">' + escapeHtml(text || 'unknown') + '</span>';
}

function resultClass(result) {
  const norm = normalize(result);
  if (norm === 'win') {
    return 'result-pill result-win';
  }
  if (norm === 'lose' || norm === 'loss') {
    return 'result-pill result-lose';
  }
  return 'result-pill result-neutral';
}

function findRun(runId) {
  return state.runs.find((run) => run.run_id === runId) || null;
}

function selectedAnchor(slot) {
  return slot === 'left' ? state.selection.right : state.selection.left;
}

function activeFieldLabels() {
  return state.fairFields
    .filter((field) => state.fairSelection.has(field.key))
    .map((field) => field.label);
}

function mismatchFields(anchor, candidate) {
  if (!anchor || state.mode !== 'fair') {
    return [];
  }
  const left = anchor.start_state || {};
  const right = candidate.start_state || {};
  return state.fairFields
    .filter((field) => state.fairSelection.has(field.key))
    .filter((field) => normalize(left[field.key]) !== normalize(right[field.key]))
    .map((field) => field.label);
}

function isCompatibleForSlot(entry, slot) {
  if (!entry.replay_available) {
    return false;
  }
  const other = selectedAnchor(slot);
  if (!other) {
    return true;
  }
  if (other.run_id === entry.run_id) {
    return false;
  }
  if (state.mode !== 'fair') {
    return true;
  }
  return mismatchFields(other, entry).length === 0;
}

function filteredRuns() {
  const query = normalize(state.search);
  return state.runs.filter((entry) => !query || normalize(entry.search_blob || '').includes(query));
}

function flash(message, persist) {
  toast.textContent = message;
  toast.classList.add('show');
  if (persist) {
    return;
  }
  window.clearTimeout(window.__arenaToastTimer);
  window.__arenaToastTimer = window.setTimeout(() => {
    toast.classList.remove('show');
  }, 2600);
}

function describeRun(entry) {
  if (!entry) {
    return '<div class="slot-empty">Nothing selected yet. Pick a saved run from the catalog.</div>';
  }
  const meta = entry.metadata || {};
  const start = entry.start_state || {};
  return [
    '<div>',
    '<strong>' + escapeHtml(entry.label) + '</strong>',
    '<div class="status-line">' + escapeHtml(entry.run_id) + '</div>',
    '<div class="slot-chips" style="margin-top:.7rem">',
    chip(meta.model || 'model unknown'),
    chip(meta.result || 'result unknown'),
    chip(start.map || 'map unknown'),
    chip(start.seed !== '' && start.seed !== null ? 'seed ' + start.seed : 'seed auto'),
    chip(start.class || 'class unknown'),
    '</div>',
    '</div>',
  ].join('');
}

function updateSummary() {
  const fairLabels = activeFieldLabels();
  document.getElementById('modeSummary').textContent = state.mode === 'fair'
    ? 'Fair Comparison on ' + (fairLabels.length ? fairLabels.join(', ') : 'no fields')
    : 'Open A/B with no start-state filtering';

  const left = state.selection.left;
  const right = state.selection.right;
  document.getElementById('selectionSummary').textContent = left && right
    ? 'Ready: ' + left.run_id + ' vs ' + right.run_id
    : left || right
      ? 'Anchor selected: ' + (left || right).run_id
      : 'Pick two runs to unlock the pairing canvas.';

  if (!state.session) {
    document.getElementById('sessionSummary').textContent = 'No replay session launched yet.';
    return;
  }
  const modeLabel = state.session.comparison_mode === 'ab'
    ? 'Open A/B'
    : state.session.comparison_mode === 'manual'
      ? 'Manual Pair'
      : 'Fair Comparison';
  document.getElementById('sessionSummary').textContent = modeLabel + ': ' + state.session.left.run_id + ' vs ' + state.session.right.run_id;
}

function renderFairFieldControls() {
  if (!state.fairFields.length) {
    fairFieldGrid.innerHTML = '<div class="status-line">Arena filters are unavailable on this server.</div>';
    return;
  }
  fairFieldGrid.innerHTML = state.fairFields.map((field) => {
    return [
      '<label class="filter-pill">',
      '<input type="checkbox" data-fair-field="', escapeHtml(field.key), '" ',
      state.fairSelection.has(field.key) ? 'checked ' : '',
      state.mode === 'fair' ? '' : 'disabled ',
      '>',
      '<span>', escapeHtml(field.label), '</span>',
      '</label>',
    ].join('');
  }).join('');
}

function renderSelection() {
  slotLeft.innerHTML = describeRun(state.selection.left);
  slotRight.innerHTML = describeRun(state.selection.right);

  let hint = 'Pick one run, then choose a compatible partner or switch to Open A/B.';
  if (!state.configured) {
    hint = 'Arena mode is not configured on this server.';
  } else if (state.mode === 'ab') {
    hint = 'Open A/B mode is active. Any two saved runs with local replays can be paired.';
  } else if (state.selection.left && !state.selection.right) {
    hint = 'Slot B is restricted to runs matching ' + state.selection.left.run_id + ' on ' + (activeFieldLabels().join(', ') || 'the selected fair fields') + '.';
  } else if (!state.selection.left && state.selection.right) {
    hint = 'Slot A is restricted to runs matching ' + state.selection.right.run_id + ' on ' + (activeFieldLabels().join(', ') || 'the selected fair fields') + '.';
  } else if (state.selection.left && state.selection.right) {
    const mismatch = mismatchFields(state.selection.left, state.selection.right);
    hint = mismatch.length
      ? 'Selected runs differ on: ' + mismatch.join(', ') + '.'
      : 'Selected runs are compatible under the active fair-match filters.';
  }

  document.getElementById('compatHint').textContent = hint;
  document.getElementById('launchBtn').disabled = !state.configured || !(state.selection.left && state.selection.right);
  configStatus.textContent = state.configured
    ? 'Arena controller is active.'
    : 'This server is not running in local arena mode. Launch it with `openra-rl arena compare`.';
}

function runCard(entry) {
  const selectedLeft = state.selection.left && state.selection.left.run_id === entry.run_id;
  const selectedRight = state.selection.right && state.selection.right.run_id === entry.run_id;
  const leftOk = state.configured && isCompatibleForSlot(entry, 'left');
  const rightOk = state.configured && isCompatibleForSlot(entry, 'right');
  const anchor = selectedAnchor('right') || selectedAnchor('left');
  const mismatch = anchor ? mismatchFields(anchor, entry) : [];
  const meta = entry.metadata || {};
  const start = entry.start_state || {};

  let note = 'Ready for comparison.';
  if (!entry.replay_available) {
    note = 'Replay file is not available locally.';
  } else if (state.mode === 'fair' && mismatch.length) {
    note = 'Fair mode mismatch: ' + mismatch.join(', ');
  }

  return [
    '<article class="run-card ',
    selectedLeft ? 'selected-left ' : '',
    selectedRight ? 'selected-right ' : '',
    state.mode === 'fair' && mismatch.length ? 'incompatible' : '',
    '">',
    '<div class="run-top"><div>',
    '<strong>', escapeHtml(entry.label), '</strong>',
    '<div class="run-id">', escapeHtml(entry.run_id), '</div>',
    '</div><span class="', resultClass(meta.result), '">', escapeHtml(meta.result || 'unknown'), '</span></div>',
    '<div class="meta-row">',
    chip(meta.model || 'model unknown'),
    chip(meta.agent_type || 'type unknown'),
    chip(meta.ticks ? String(meta.ticks) + ' ticks' : 'ticks unknown'),
    '</div>',
    '<div class="meta-row">',
    chip(start.map || 'map unknown'),
    chip(start.seed !== '' && start.seed !== null ? 'seed ' + start.seed : 'seed auto'),
    chip(start.class || 'class unknown'),
    chip(start.opponent || 'opponent unknown'),
    chip(start.faction || 'faction unknown'),
    '</div>',
    '<div class="status-line">', escapeHtml(note), '</div>',
    '<div class="run-actions">',
    '<button type="button" class="slot-btn" data-pick-slot="left" data-run-id="', escapeHtml(entry.run_id), '" ', leftOk ? '' : 'disabled', '>Use as A</button>',
    '<button type="button" class="slot-btn" data-pick-slot="right" data-run-id="', escapeHtml(entry.run_id), '" ', rightOk ? '' : 'disabled', '>Use as B</button>',
    '</div></article>',
  ].join('');
}

function renderCatalog() {
  const runs = filteredRuns();
  document.getElementById('catalogStats').textContent = runs.length + ' visible of ' + state.runs.length + ' saved runs';
  runGrid.innerHTML = runs.length
    ? runs.map((entry) => runCard(entry)).join('')
    : '<div class="empty-state">No saved runs match the current search.</div>';
}

function buildViewerUrl(entry) {
  return 'http://127.0.0.1:' + entry.port + '/vnc.html?autoconnect=1&resize=scale&quality=8&compression=4';
}

function viewerCard(entry) {
  const meta = entry.metadata || {};
  const stageId = entry.slot === 'left' ? 'viewerLeft' : 'viewerRight';
  const statusId = entry.slot === 'left' ? 'viewerLeftStatus' : 'viewerRightStatus';
  const label = entry.slot === 'left' ? 'A' : 'B';
  const rawUrl = buildViewerUrl(entry);
  const start = entry.start_state || {};
  return [
    '<article class="viewer-card">',
    '<div class="viewer-top"><div style="display:flex;gap:.75rem;align-items:flex-start;">',
    '<div class="viewer-label ', entry.slot, '">', label, '</div>',
    '<div><strong>', escapeHtml(entry.label), '</strong><div class="status-line">', escapeHtml(entry.run_id), '</div></div>',
    '</div><span class="', resultClass(meta.result), '">', escapeHtml(meta.result || 'unknown'), '</span></div>',
    '<div class="viewer-chip-row">',
    chip(meta.model || 'model unknown'),
    chip(meta.map || start.map || 'map unknown'),
    chip(meta.seed !== '' && meta.seed !== null ? 'seed ' + meta.seed : (start.seed !== '' && start.seed !== null ? 'seed ' + start.seed : 'seed auto')),
    chip(meta.class || start.class || 'class unknown'),
    chip(meta.engine_version || start.engine_version || 'engine unknown'),
    '</div>',
    '<div class="viewer-stage" id="', stageId, '"><div class="placeholder">Waiting for replay canvas...</div></div>',
    '<div class="viewer-status" id="', statusId, '">Idle.</div>',
    '<div class="viewer-toolbar">',
    '<button type="button" class="btn-ghost" data-open-raw="', escapeHtml(rawUrl), '">Open Raw Viewer</button>',
    '<button type="button" class="btn-ghost" data-copy-raw="', escapeHtml(rawUrl), '">Copy Raw URL</button>',
    '</div>',
    '<div class="vote-row">',
    '<button type="button" class="vote-btn ', entry.slot === 'left' ? 'vote-left' : 'vote-right', '" data-vote="', entry.slot, '">Prefer ', label, '</button>',
    '<button type="button" class="btn-ghost" data-reconnect-slot="', entry.slot, '">Reconnect ', label, '</button>',
    '</div>',
    '</article>',
  ].join('');
}

function ensureComposer(slot) {
  const root = document.getElementById(slot === 'left' ? 'viewerLeft' : 'viewerRight');
  const statusNode = document.getElementById(slot === 'left' ? 'viewerLeftStatus' : 'viewerRightStatus');
  if (!root || !statusNode) {
    return null;
  }
  const current = state.composers[slot];
  if (current && current.root === root && current.statusNode === statusNode) {
    return current;
  }
  const composer = new ReplayComposer(slot, root, statusNode);
  state.composers[slot] = composer;
  return composer;
}

function disconnectComposers() {
  Object.values(state.composers).forEach((composer) => {
    if (composer) {
      composer.disconnect();
    }
  });
}

function attachComposers(force) {
  if (!state.session) {
    disconnectComposers();
    return;
  }
  const leftComposer = ensureComposer('left');
  const rightComposer = ensureComposer('right');
  if (leftComposer) {
    leftComposer.connect(state.session.left, Boolean(force));
  }
  if (rightComposer) {
    rightComposer.connect(state.session.right, Boolean(force));
  }
}

function renderCompare() {
  if (!state.session) {
    compareMeta.textContent = 'Launch a pair to render both replay canvases below.';
    compareBody.innerHTML = '<div class="empty-state">No active session. Select two runs, launch the comparison, then vote here.</div>';
    disconnectComposers();
    return;
  }

  const modeLabel = state.session.comparison_mode === 'ab'
    ? 'Open A/B'
    : state.session.comparison_mode === 'manual'
      ? 'Manual Pair'
      : 'Fair Comparison';
  const fields = Array.isArray(state.session.fair_fields) && state.session.fair_fields.length
    ? state.session.fair_fields.join(', ')
    : 'none';
  compareMeta.textContent = modeLabel + ': ' + state.session.left.run_id + ' vs ' + state.session.right.run_id + ' (' + fields + ')';
  compareBody.innerHTML = '<div class="compare-grid">' + viewerCard(state.session.left) + viewerCard(state.session.right) + '</div>';
  attachComposers(false);
}

function renderModeButtons() {
  modeFairBtn.classList.toggle('active', state.mode === 'fair');
  modeAbBtn.classList.toggle('active', state.mode === 'ab');
}

function renderAll() {
  renderModeButtons();
  renderFairFieldControls();
  renderSelection();
  renderCatalog();
  renderCompare();
  updateSummary();
  if (!state.configured) {
    statusLine.textContent = 'Arena mode is unavailable until `openra-rl arena compare` starts the local controller.';
  } else if (state.session) {
    statusLine.textContent = 'Replay viewers are connected into the pairing page.';
  } else {
    statusLine.textContent = 'Ready.';
  }
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (error) {
    return {};
  }
}

function apiError(payload, fallback) {
  return payload.error || payload.detail || fallback;
}

async function refreshCatalog() {
  const response = await fetch('/arena/state');
  const payload = await readJson(response);
  if (!response.ok) {
    flash(apiError(payload, 'Failed to refresh arena state.'), false);
    return;
  }
  state.configured = Boolean(payload.configured);
  state.runs = Array.isArray(payload.runs) ? payload.runs : [];
  if (!state.session && payload.session) {
    state.session = payload.session;
  }
  renderAll();
}

async function launchComparison() {
  if (!(state.selection.left && state.selection.right)) {
    flash('Select two runs first.', false);
    return;
  }
  statusLine.textContent = 'Launching replay viewers...';
  const response = await fetch('/arena/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      left_run_id: state.selection.left.run_id,
      right_run_id: state.selection.right.run_id,
      comparison_mode: state.mode,
      fair_fields: Array.from(state.fairSelection),
    }),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    const message = apiError(payload, 'Failed to start comparison.');
    statusLine.textContent = message;
    flash(message, false);
    return;
  }
  state.session = payload.session;
  state.selection.left = payload.session.left;
  state.selection.right = payload.session.right;
  renderAll();
  attachComposers(true);
  flash('Comparison session started.', false);
}

async function savePreference(action) {
  if (!state.session) {
    flash('Launch a comparison before voting.', false);
    return;
  }
  const response = await fetch('/arena/preferences', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ preferred_side: action }),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    const message = apiError(payload, 'Failed to save preference.');
    statusLine.textContent = message;
    flash(message, false);
    return;
  }
  statusLine.textContent = 'Saved: ' + payload.path;
  flash('Preference saved to ' + payload.path, true);
}

async function stopSession() {
  const response = await fetch('/arena/session', { method: 'DELETE' });
  const payload = await readJson(response);
  if (!response.ok) {
    const message = apiError(payload, 'Failed to stop viewers.');
    statusLine.textContent = message;
    flash(message, false);
    return;
  }
  state.session = null;
  renderAll();
  flash('Replay viewers stopped.', false);
}

document.getElementById('searchInput').addEventListener('input', (event) => {
  state.search = event.target.value || '';
  renderCatalog();
});

modeFairBtn.addEventListener('click', () => {
  state.mode = 'fair';
  renderAll();
});

modeAbBtn.addEventListener('click', () => {
  state.mode = 'ab';
  renderAll();
});

fairFieldGrid.addEventListener('change', (event) => {
  const field = event.target.getAttribute('data-fair-field');
  if (!field) {
    return;
  }
  if (event.target.checked) {
    state.fairSelection.add(field);
  } else {
    state.fairSelection.delete(field);
  }
  renderAll();
});

document.addEventListener('click', (event) => {
  const pickSlot = event.target.getAttribute('data-pick-slot');
  if (pickSlot) {
    const entry = findRun(event.target.getAttribute('data-run-id'));
    if (entry) {
      state.selection[pickSlot] = entry;
      renderAll();
    }
    return;
  }

  const clearSlot = event.target.getAttribute('data-clear-slot');
  if (clearSlot) {
    state.selection[clearSlot] = null;
    renderAll();
    return;
  }

  const vote = event.target.getAttribute('data-vote');
  if (vote) {
    savePreference(vote);
    return;
  }

  const rawUrl = event.target.getAttribute('data-open-raw');
  if (rawUrl) {
    window.open(rawUrl, '_blank', 'noopener');
    return;
  }

  const copyRaw = event.target.getAttribute('data-copy-raw');
  if (copyRaw) {
    navigator.clipboard.writeText(copyRaw)
      .then(() => flash('Replay URL copied.', false))
      .catch(() => flash(copyRaw, true));
    return;
  }

  const reconnectSlot = event.target.getAttribute('data-reconnect-slot');
  if (reconnectSlot && state.session) {
    const composer = ensureComposer(reconnectSlot);
    if (composer) {
      composer.connect(state.session[reconnectSlot], true);
      flash('Reconnecting ' + (reconnectSlot === 'left' ? 'A' : 'B') + '...', false);
    }
  }
});

document.getElementById('launchBtn').addEventListener('click', launchComparison);
document.getElementById('resetSelectionBtn').addEventListener('click', () => {
  state.selection.left = null;
  state.selection.right = null;
  renderAll();
});
document.getElementById('refreshCatalogBtn').addEventListener('click', refreshCatalog);
document.getElementById('refreshViewersBtn').addEventListener('click', () => {
  attachComposers(true);
  flash('Reconnect requested for both viewers.', false);
});
document.getElementById('skipBtn').addEventListener('click', () => savePreference('skip'));
document.getElementById('stopSessionBtn').addEventListener('click', stopSession);

document.addEventListener('keydown', (event) => {
  if (!state.session) {
    return;
  }
  if (event.key === '1') {
    savePreference('left');
  } else if (event.key === '2') {
    savePreference('right');
  } else if (event.key.toLowerCase() === 's') {
    savePreference('skip');
  }
});

renderAll();
""".replace("__STATE__", state_json)
