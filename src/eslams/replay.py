# ruff: noqa: E501
"""Local replay HTML renderer."""

from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any


def render_replay_html(artifact_path: Path, output_path: Path | None = None) -> Path:
    artifact_path = artifact_path.resolve()
    if artifact_path.is_dir():
        events = _read_replay_events(artifact_path)
        output = output_path or artifact_path / "replay" / "index.html"
        return _write_replay(output, events)
    if zipfile.is_zipfile(artifact_path):
        with tempfile.TemporaryDirectory(prefix="eslams-replay-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            with zipfile.ZipFile(artifact_path) as archive:
                archive.extractall(tmp_path)
            events = _read_replay_events(tmp_path)
        output = output_path or artifact_path.with_suffix(".replay.html")
        return _write_replay(output, events)
    raise FileNotFoundError(artifact_path)


def _read_replay_events(artifact_path: Path) -> list[dict[str, Any]]:
    replay_file = artifact_path / "replay" / "replay_events.jsonl"
    return [
        json.loads(line)
        for line in replay_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_replay(output_path: Path, events: list[dict[str, Any]]) -> Path:
    payload = json.dumps(events, ensure_ascii=False).replace("</", "<\\/")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_html(payload), encoding="utf-8")
    return output_path


def _html(events_json: str) -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>eSlams Replay</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #080b10;
      --panel: #101621;
      --panel-strong: #14231f;
      --line: #263447;
      --line-hot: #78efc3;
      --text: #eef5ff;
      --muted: #98a9bf;
      --gold: #ecd98b;
      --blue-square: #647d9f;
      --cream-square: #ead68e;
      --danger: #ff6d7a;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main {
      width: min(100%, 1320px);
      margin: 0 auto;
      padding: 24px;
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 20px;
      padding-bottom: 16px;
    }
    h1 {
      margin: 0;
      font-size: 48px;
      line-height: 1;
      letter-spacing: 0;
    }
    button {
      min-height: 40px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #111a27;
      color: var(--text);
      font: inherit;
      cursor: pointer;
    }
    button:hover { border-color: var(--line-hot); }
    .muted { color: var(--muted); }
    .shell {
      display: grid;
      grid-template-columns: minmax(190px, .72fr) minmax(420px, 1.55fr) minmax(190px, .72fr);
      gap: 16px;
      align-items: stretch;
      min-height: calc(100vh - 124px);
    }
    .agent, .stage {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      min-width: 0;
      max-width: 100%;
    }
    .agent {
      display: flex;
      flex-direction: column;
      padding: 14px;
      overflow: hidden;
    }
    .agent.active {
      border-color: var(--line-hot);
      background: var(--panel-strong);
    }
    .agent-label {
      margin: 0 0 8px;
      color: var(--line-hot);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
    }
    .agent-name {
      margin: 0 0 14px;
      font-size: 20px;
      font-weight: 800;
      overflow-wrap: anywhere;
    }
    .move-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-height: 0;
      overflow: auto;
      padding-right: 3px;
    }
    .move {
      width: 100%;
      min-height: 0;
      text-align: left;
      padding: 8px 9px;
      background: #0b111a;
    }
    .move[aria-current="true"] {
      border-color: var(--line-hot);
      background: rgba(120, 239, 195, .14);
    }
    .move-title {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      font-size: 12px;
      font-weight: 800;
    }
    .move-hash {
      margin-top: 3px;
      color: var(--muted);
      font-size: 11px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .stage {
      display: grid;
      grid-template-rows: auto minmax(0, 1fr) auto;
      gap: 12px;
      padding: 14px;
    }
    .status {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: start;
    }
    .turn {
      min-width: 0;
      font-size: 14px;
      color: var(--muted);
    }
    .turn strong {
      display: block;
      color: var(--text);
      font-size: 18px;
      margin-bottom: 4px;
    }
    .turn span {
      display: block;
      overflow-wrap: anywhere;
    }
    .controls {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: end;
    }
    .controls button {
      min-width: 72px;
      padding: 0 12px;
    }
    #play {
      min-width: 92px;
      background: var(--line-hot);
      border-color: var(--line-hot);
      color: #06100d;
      font-weight: 800;
    }
    .board-host {
      display: grid;
      place-items: center;
      min-height: 0;
      max-width: 100%;
    }
    .chess-frame {
      display: grid;
      grid-template-columns: 26px minmax(0, 1fr);
      grid-template-rows: minmax(0, 1fr) 24px;
      width: min(100%, 620px);
      max-width: 100%;
    }
    .rank-labels {
      display: grid;
      grid-template-rows: repeat(8, 1fr);
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      align-items: center;
      justify-items: center;
    }
    .file-labels {
      grid-column: 2;
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      align-items: center;
      justify-items: center;
    }
    .chessboard {
      display: grid;
      grid-template-columns: repeat(8, 1fr);
      width: 100%;
      aspect-ratio: 1;
      overflow: hidden;
      border: 1px solid #0d1420;
      border-radius: 6px;
      box-shadow: 0 18px 50px rgba(0, 0, 0, .28);
      min-width: 0;
    }
    .square {
      position: relative;
      display: grid;
      place-items: center;
      aspect-ratio: 1;
    }
    .square.light { background: var(--cream-square); }
    .square.dark { background: var(--blue-square); }
    .square.last::after {
      content: "";
      position: absolute;
      inset: 8%;
      border: 3px solid rgba(120, 239, 195, .8);
      border-radius: 5px;
      pointer-events: none;
    }
    .piece {
      position: relative;
      z-index: 1;
      font-family: "Arial Unicode MS", "DejaVu Sans", "Noto Sans Symbols 2", serif;
      font-size: clamp(30px, 7vw, 62px);
      line-height: 1;
    }
    .piece-white {
      color: #fbfdff;
      text-shadow: 0 2px 3px rgba(0, 0, 0, .65);
    }
    .piece-black {
      color: #101722;
      -webkit-text-stroke: 1px rgba(255, 255, 255, .72);
      text-shadow: 0 1px 0 rgba(255, 255, 255, .85);
    }
    .grid-board {
      display: grid;
      gap: 8px;
      width: min(100%, 560px);
    }
    .grid-cell {
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #0b111a;
      font-size: 34px;
      font-weight: 900;
    }
    .disc-r { color: #ff6575; }
    .disc-y { color: var(--gold); }
    .details {
      display: grid;
      gap: 8px;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      color: var(--muted);
      font-size: 12px;
    }
    .detail {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px;
      background: #0b111a;
    }
    .detail strong {
      display: block;
      color: var(--text);
      margin-bottom: 4px;
      overflow-wrap: anywhere;
    }
    pre {
      margin: 0;
      max-width: 100%;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--muted);
    }
    @media (max-width: 980px) {
      main { padding: 16px; }
      header { align-items: start; flex-direction: column; }
      h1 { font-size: 36px; }
      .shell { grid-template-columns: 1fr; min-height: 0; }
      .agent { max-height: 280px; }
      .details { grid-template-columns: 1fr; }
      .status { grid-template-columns: 1fr; }
      .controls { justify-content: start; }
      .board-host { place-items: start; }
      .chess-frame {
        grid-template-columns: 22px minmax(0, 1fr);
        width: calc(100vw - 68px);
        max-width: 100%;
      }
      .piece { font-size: clamp(22px, 7vw, 30px); }
    }
  </style>
</head>
<body>
<main>
  <header>
    <div>
      <h1>Replay</h1>
      <div class="muted" id="runId">Local run</div>
    </div>
    <div class="muted" id="sourceLabel">Generated from public replay events</div>
  </header>
  <section class="shell">
    <aside class="agent" id="panel-player_1">
      <p class="agent-label">Agent 1</p>
      <p class="agent-name">player_1</p>
      <div class="move-list" id="moves-player_1"></div>
    </aside>
    <section class="stage">
      <div class="status">
        <div class="turn" id="turnStatus"></div>
        <div class="controls">
          <button id="prev" type="button">Prev</button>
          <button id="play" type="button">Play</button>
          <button id="next" type="button">Next</button>
        </div>
      </div>
      <div class="board-host" id="board"></div>
      <div class="details" id="details"></div>
    </section>
    <aside class="agent" id="panel-player_2">
      <p class="agent-label">Agent 2</p>
      <p class="agent-name">player_2</p>
      <div class="move-list" id="moves-player_2"></div>
    </aside>
  </section>
</main>
<script type="application/json" id="events">""" + events_json + """</script>
<script>
const events = JSON.parse(document.getElementById('events').textContent);
let selected = 0;
let timer = null;
const files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const ranks = ['8', '7', '6', '5', '4', '3', '2', '1'];
const glyphs = {
  P: '♙', N: '♘', B: '♗', R: '♖', Q: '♕', K: '♔',
  p: '♟', n: '♞', b: '♝', r: '♜', q: '♛', k: '♚'
};

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function shortHash(value) {
  return String(value || '').slice(0, 18);
}

function moveEntries() {
  return events.slice(1).map((event, offset) => {
    const index = offset + 1;
    const previous = events[index - 1] || {};
    return { event, index, mover: previous.active_player || event.active_player };
  });
}

function currentMove() {
  return moveEntries().find((item) => item.index === selected) || null;
}

function labelForAction(item) {
  if (!item) return 'initial';
  const state = item.event.public_state || {};
  return state.last_move_san || state.last_move_uci || item.event.action || 'move';
}

function setSelected(index) {
  selected = Math.max(0, Math.min(index, events.length - 1));
  render();
}

function togglePlay() {
  if (timer) {
    clearInterval(timer);
    timer = null;
    render();
    return;
  }
  if (selected >= events.length - 1) selected = 0;
  timer = setInterval(() => {
    if (selected >= events.length - 1) {
      clearInterval(timer);
      timer = null;
      render();
      return;
    }
    selected += 1;
    render();
  }, 760);
  render();
}

function renderMoves(player) {
  const list = document.getElementById(`moves-${player}`);
  const items = moveEntries().filter((item) => item.mover === player);
  list.innerHTML = items.map((item) => `
    <button class="move" type="button" aria-current="${item.index === selected}" onclick="setSelected(${item.index})">
      <span class="move-title">
        <span>Turn ${escapeHtml(item.event.turn_id)}</span>
        <span>${escapeHtml(labelForAction(item))}</span>
      </span>
      <span class="move-hash">${escapeHtml(shortHash(item.event.state_hash))}</span>
    </button>
  `).join('') || '<div class="muted">No moves yet</div>';
}

function renderChess(event) {
  const state = event.public_state || {};
  const fen = String(state.fen || '');
  const placement = fen.split(' ')[0] || '';
  const last = String(state.last_move_uci || '');
  const lastSquares = new Set(last.length >= 4 ? [last.slice(0, 2), last.slice(2, 4)] : []);
  const stacked = window.matchMedia('(max-width: 980px)').matches;
  const frameLimit = stacked ? 322 : 620;
  const frameWidth = Math.floor(Math.max(240, Math.min(frameLimit, window.innerWidth - 68)));
  const cells = [];
  placement.split('/').forEach((rank, row) => {
    let col = 0;
    for (const char of rank) {
      if (/\\d/.test(char)) {
        const empty = Number(char);
        for (let i = 0; i < empty; i += 1) cells.push(chessCell(row, col++, '', lastSquares));
      } else {
        cells.push(chessCell(row, col++, char, lastSquares));
      }
    }
  });
  while (cells.length < 64) cells.push(chessCell(Math.floor(cells.length / 8), cells.length % 8, '', lastSquares));
  return `
    <div class="chess-frame" style="width: ${frameWidth}px">
      <div class="rank-labels">${ranks.map((rank) => `<span>${rank}</span>`).join('')}</div>
      <div class="chessboard" aria-label="Chess board">${cells.join('')}</div>
      <div></div>
      <div class="file-labels">${files.map((file) => `<span>${file}</span>`).join('')}</div>
    </div>
  `;
}

function chessCell(row, col, piece, lastSquares) {
  const square = `${files[col] || ''}${ranks[row] || ''}`;
  const tone = (row + col) % 2 === 0 ? 'light' : 'dark';
  const side = piece ? (piece === piece.toUpperCase() ? 'white' : 'black') : '';
  const last = lastSquares.has(square) ? ' last' : '';
  const content = piece ? `<span class="piece piece-${side}" aria-label="${side} ${piece}">${glyphs[piece] || piece}</span>` : '';
  return `<div class="square ${tone}${last}" data-square="${square}">${content}</div>`;
}

function renderGrid(event) {
  const state = event.public_state || {};
  const board = state.board;
  if (!Array.isArray(board)) return `<pre>${escapeHtml(JSON.stringify(state, null, 2))}</pre>`;
  const rows = Array.isArray(board[0]) ? board : chunkBoard(board, state.rows || 3);
  const cols = rows[0]?.length || 1;
  const cells = rows.flat().map((cell) => {
    const cls = cell === 'R' ? 'disc-r' : cell === 'Y' ? 'disc-y' : '';
    return `<div class="grid-cell ${cls}">${escapeHtml(cell || '')}</div>`;
  }).join('');
  return `<div class="grid-board" style="grid-template-columns: repeat(${cols}, 1fr)">${cells}</div>`;
}

function chunkBoard(board, rows) {
  const cols = Math.max(1, Math.ceil(board.length / rows));
  const out = [];
  for (let index = 0; index < board.length; index += cols) out.push(board.slice(index, index + cols));
  return out;
}

function renderBoard(event) {
  const state = event.public_state || {};
  if (state.fen || event.render_hints?.renderer === 'chessboard') return renderChess(event);
  return renderGrid(event);
}

function renderDetails(event, move) {
  const state = event.public_state || {};
  const validation = state.final_validation || {};
  const terminal = state.terminal_reason || event.terminal;
  return [
    ['Move', move ? `${move.mover} -> ${labelForAction(move)}` : 'initial'],
    ['FEN', state.fen || 'n/a'],
    ['Validation', `check=${validation.check ?? 'n/a'} checkmate=${validation.checkmate ?? 'n/a'} legal=${validation.legal_move_count ?? 'n/a'}`],
    ['Winner', state.winner || event.scores && winnerFromScores(event.scores) || 'none'],
    ['Terminal', terminal || 'false'],
    ['Scores', JSON.stringify(event.scores || {})]
  ].map(([label, value]) => `
    <div class="detail">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(value)}</span>
    </div>
  `).join('');
}

function winnerFromScores(scores) {
  const entries = Object.entries(scores);
  if (!entries.length) return null;
  const max = Math.max(...entries.map(([, score]) => Number(score)));
  if (max <= 0) return null;
  const winners = entries.filter(([, score]) => Number(score) === max);
  return winners.length === 1 ? winners[0][0] : null;
}

function render() {
  const event = events[selected] || {};
  const move = currentMove();
  document.getElementById('runId').textContent = event.run_id || events[0]?.run_id || 'Local run';
  document.getElementById('turnStatus').innerHTML = `
    <strong>${move ? `Turn ${event.turn_id}: ${escapeHtml(labelForAction(move))}` : 'Initial position'}</strong>
    <span>Frame ${selected + 1} / ${events.length} · active ${escapeHtml(event.active_player || 'n/a')} · hash ${escapeHtml(shortHash(event.state_hash))}</span>
  `;
  document.getElementById('play').textContent = timer ? 'Pause' : 'Play';
  document.getElementById('prev').disabled = selected === 0;
  document.getElementById('next').disabled = selected >= events.length - 1;
  document.getElementById('board').innerHTML = renderBoard(event);
  document.getElementById('details').innerHTML = renderDetails(event, move);
  for (const player of ['player_1', 'player_2']) {
    document.getElementById(`panel-${player}`).classList.toggle('active', move?.mover === player);
    renderMoves(player);
  }
}

document.getElementById('prev').addEventListener('click', () => setSelected(selected - 1));
document.getElementById('next').addEventListener('click', () => setSelected(selected + 1));
document.getElementById('play').addEventListener('click', togglePlay);
window.addEventListener('resize', render);
render();
</script>
</body>
</html>
"""
