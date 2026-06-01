# ruff: noqa: E501
"""Local replay HTML renderer."""

from __future__ import annotations

import html
import json
from pathlib import Path


def render_replay_html(artifact_path: Path, output_path: Path | None = None) -> Path:
    artifact_path = artifact_path.resolve()
    output_path = output_path or artifact_path / "replay" / "index.html"
    replay_file = artifact_path / "replay" / "replay_events.jsonl"
    events = [json.loads(line) for line in replay_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = html.escape(json.dumps(events, ensure_ascii=False))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html(payload), encoding="utf-8")
    return output_path


def _html(events_json: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>eSlams Replay</title>
  <style>
    :root {{ color-scheme: dark; --bg: #07090d; --panel: #111722; --line: #243043; --text: #edf4ff; --muted: #8ea0b8; --accent: #72f5bf; --gold: #f5d26c; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: radial-gradient(circle at top left, #152235 0, #07090d 34rem); color: var(--text); }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ display: flex; justify-content: space-between; align-items: center; gap: 24px; margin-bottom: 24px; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 6vw, 4.5rem); letter-spacing: 0; line-height: .92; }}
    .meta {{ color: var(--muted); font-size: 14px; }}
    .stage {{ display: grid; grid-template-columns: minmax(280px, 1fr) 320px; gap: 20px; align-items: start; }}
    .board {{ border: 1px solid var(--line); background: rgba(17, 23, 34, .86); border-radius: 8px; padding: 18px; min-height: 520px; }}
    .timeline {{ border: 1px solid var(--line); background: rgba(17, 23, 34, .74); border-radius: 8px; overflow: hidden; }}
    .timeline button {{ width: 100%; text-align: left; color: var(--text); background: transparent; border: 0; border-bottom: 1px solid var(--line); padding: 12px 14px; cursor: pointer; }}
    .timeline button[aria-current="true"] {{ background: rgba(114, 245, 191, .12); }}
    .grid {{ display: grid; gap: 8px; width: min(100%, 520px); margin: 18px auto; }}
    .cell {{ aspect-ratio: 1; display: grid; place-items: center; border: 1px solid var(--line); border-radius: 6px; background: #0b1018; font-weight: 800; font-size: clamp(1.4rem, 6vw, 3.2rem); }}
    .disc-r {{ color: #ff5c6c; }} .disc-y {{ color: #f5d26c; }}
    pre {{ white-space: pre-wrap; word-break: break-word; color: var(--muted); }}
    @media (max-width: 840px) {{ .stage {{ grid-template-columns: 1fr; }} header {{ align-items: flex-start; flex-direction: column; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Replay</h1>
      <div class="meta" id="run"></div>
    </div>
    <div class="meta">Artifact-backed public trace</div>
  </header>
  <section class="stage">
    <div class="board" id="board"></div>
    <nav class="timeline" id="timeline" aria-label="Replay timeline"></nav>
  </section>
</main>
<script type="application/json" id="events">{events_json}</script>
<script>
const events = JSON.parse(document.getElementById('events').textContent);
let selected = events.length - 1;
document.getElementById('run').textContent = events[0]?.run_id || 'Local run';
function renderGrid(event) {{
  const state = event.public_state;
  const board = state.board;
  if (!Array.isArray(board)) return '<pre>' + JSON.stringify(state, null, 2) + '</pre>';
  const rows = Array.isArray(board[0]) ? board : [board.slice(0,3), board.slice(3,6), board.slice(6,9)];
  const cols = rows[0].length;
  const cells = rows.flat().map((cell) => {{
    const cls = cell === 'R' ? 'disc-r' : cell === 'Y' ? 'disc-y' : '';
    return `<div class="cell ${{cls}}">${{cell || ''}}</div>`;
  }}).join('');
  return `<div class="grid" style="grid-template-columns: repeat(${{cols}}, 1fr)">${{cells}}</div>`;
}}
function render() {{
  const event = events[selected];
  document.getElementById('board').innerHTML = `
    <div class="meta">Turn ${{event.turn_id}} | Active ${{event.active_player}} | Hash ${{event.state_hash}}</div>
    ${{renderGrid(event)}}
    <pre>${{JSON.stringify({{ action: event.action, scores: event.scores, markers: event.markers, terminal: event.terminal }}, null, 2)}}</pre>`;
  document.getElementById('timeline').innerHTML = events.map((item, index) => `
    <button aria-current="${{index === selected}}" onclick="selected=${{index}};render()">
      Turn ${{item.turn_id}} · ${{item.action ?? 'initial'}}<br><span class="meta">${{item.state_hash.slice(0, 24)}}...</span>
    </button>`).join('');
}}
render();
</script>
</body>
</html>
"""
