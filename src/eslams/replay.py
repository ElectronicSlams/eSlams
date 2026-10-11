# ruff: noqa: E501
"""Local replay HTML renderer."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from eslams.output import write_text_file


def render_replay_html(
    artifact_path: Path, output_path: Path | None = None, *, overwrite: bool = False,
    diagnostic: bool = False,
) -> Path:
    # Local import avoids the pre-manifest writer's circular dependency.
    from eslams.artifacts import ArtifactValidator, open_artifact

    artifact_path = artifact_path.resolve()
    name = artifact_path.name.removesuffix(".eslams.d").removesuffix(".eslams")
    output = output_path or artifact_path.with_name(f"{name}.replay.html")
    with open_artifact(artifact_path) as root:
        report = ArtifactValidator().validate_report(root, profile="auto")
        if not report.valid and not diagnostic:
            raise ValueError("artifact failed validation: " + "; ".join(report.errors))
        if diagnostic:
            status = "DIAGNOSTIC — UNTRUSTED REPLAY. " + (
                "; ".join(report.errors) if report.errors else "Explicit diagnostic mode."
            )
        else:
            status = "Content validated. Signature: " + report.signature.status + "."
        events = _read_replay_events(root)
    return _write_replay(output, events, overwrite=overwrite, source=artifact_path, status=status)


def _read_replay_events(artifact_path: Path) -> list[dict[str, Any]]:
    replay_file = artifact_path / "replay" / "replay_events.jsonl"
    return [
        json.loads(line)
        for line in replay_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_artifact_replay(artifact_path: Path) -> Path:
    """Create the in-artifact replay before the artifact writer hashes it."""
    return _write_replay(artifact_path / "replay" / "index.html", _read_replay_events(artifact_path))


def _write_replay(
    output_path: Path,
    events: list[dict[str, Any]],
    *,
    overwrite: bool = False,
    source: Path | None = None,
    status: str = "Embedded preview — validate the complete artifact before trusting it.",
) -> Path:
    payload = json.dumps(events, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return write_text_file(
        output_path, _html(payload, status), overwrite=overwrite, sources=[] if source is None else [source]
    )


def _html(events_json: str, status: str) -> str:
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
    .agent-column {
      display: grid;
      gap: 16px;
      align-content: start;
      min-width: 0;
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
      min-height: 40px;
      flex: 0 0 auto;
      text-align: left;
      padding: 8px 9px;
      background: #0b111a;
    }
    button:focus-visible { outline: 3px solid var(--line-hot); outline-offset: 2px; }
    #leftAgents { order: 1; }
    #rightAgents { order: 3; }
    .stage { order: 2; }
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
      min-width: 0;
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
      gap: 2px;
      width: min(100%, 560px);
      min-width: 0;
    }
    .grid-cell {
      aspect-ratio: 1;
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #0b111a;
      min-width: 0;
      overflow-wrap: anywhere;
      overflow: hidden;
      font-size: clamp(9px, 3vw, 28px);
      font-weight: 900;
    }
    .board-row { display: contents; }
    .state-summary { width: 100%; min-width: 0; overflow-wrap: anywhere; }
    .state-summary dl { display: grid; grid-template-columns: minmax(70px, .6fr) minmax(0, 1fr); gap: 8px; margin: 0; }
    .state-summary dt { color: var(--muted); }
    .state-summary dd { margin: 0; min-width: 0; }
    .state-summary ul, .state-summary ol { padding-left: 20px; margin: 0; }
    .state-summary li { margin-bottom: 4px; }
    #artifactTrust, #sourceLabel, #runId { overflow-wrap: anywhere; min-width: 0; }
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
      .stage { order: 0; }
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
  <p role="status" id="artifactTrust">""" + html.escape(status) + """</p>
  <section class="shell">
    <section class="stage">
      <div class="status">
        <div class="turn" id="turnStatus" role="status" aria-live="polite" aria-atomic="true"></div>
        <div class="controls">
          <button id="prev" type="button" aria-controls="board" aria-keyshortcuts="ArrowLeft">Prev</button>
          <button id="play" type="button">Play</button>
          <button id="next" type="button" aria-controls="board" aria-keyshortcuts="ArrowRight">Next</button>
        </div>
      </div>
      <div class="board-host" id="board"></div>
      <div class="details" id="details"></div>
    </section>
    <div class="agent-column" id="leftAgents"></div>
    <div class="agent-column" id="rightAgents"></div>
  </section>
</main>
<script type="application/json" id="events">""" + events_json + """</script>
<script>
const events = JSON.parse(document.getElementById('events').textContent);
let selected = 0;
let timer = null;
let players = [];
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

function replayPlayers() {
  const seen = new Set();
  for (const event of events) {
    for (const candidate of [event.active_player, event.actor_player, event.seat]) {
      if (candidate) seen.add(String(candidate));
    }
    if (event.scores && typeof event.scores === 'object') {
      Object.keys(event.scores).forEach((player) => seen.add(player));
    }
  }
  for (const move of moveEntries()) {
    if (move.mover) seen.add(String(move.mover));
  }
  return [...seen].sort();
}

function renderPlayerPanels() {
  players = replayPlayers();
  if (players.length === 0) players = ['player_1', 'player_2'];
  const midpoint = Math.ceil(players.length / 2);
  const columns = [
    [document.getElementById('leftAgents'), players.slice(0, midpoint)],
    [document.getElementById('rightAgents'), players.slice(midpoint)],
  ];
  for (const [column, columnPlayers] of columns) {
    column.innerHTML = columnPlayers.map((player) => {
      const index = players.indexOf(player) + 1;
      return `
        <aside class="agent" id="panel-${escapeHtml(player)}">
          <p class="agent-label">Agent ${escapeHtml(index)}</p>
          <p class="agent-name">${escapeHtml(player)}</p>
          <div class="move-list" id="moves-${escapeHtml(player)}"></div>
        </aside>
      `;
    }).join('');
  }
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
  const label = state.last_move_san ?? state.last_move_uci ?? item.event.action_label ?? item.event.action;
  return label == null ? 'hidden action' : typeof label === 'object' ? JSON.stringify(label) : String(label);
}

function setSelected(index) {
  if (timer) { clearInterval(timer); timer = null; }
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
  if (!list) return;
  const items = moveEntries().filter((item) => item.mover === player);
  if (!list.dataset.initialized) {
    list.dataset.initialized = 'true';
    list.setAttribute('aria-label', `${player} moves`);
    list.innerHTML = items.map((item) => `
      <button class="move" type="button" data-event-index="${item.index}" aria-current="false" onclick="setSelected(${item.index})">
        <span class="move-title">
          <span>Turn ${escapeHtml(item.event.turn_id)}</span>
          <span>${escapeHtml(labelForAction(item))}</span>
        </span>
        <span class="move-hash">${escapeHtml(shortHash(item.event.state_hash))}</span>
      </button>
    `).join('') || '<div class="muted">No moves yet</div>';
  }
  const anchor = items.find((item) => item.index === selected) || items.filter((item) => item.index < selected).at(-1) || items[0];
  for (const button of list.querySelectorAll('button')) {
    const index = Number(button.dataset.eventIndex);
    button.setAttribute('aria-current', String(index === selected));
    button.tabIndex = index === anchor?.index ? 0 : -1;
  }
}

function renderChess(event) {
  const state = event.public_state || {};
  const fen = String(state.fen || '');
  const placement = fen.split(' ')[0] || '';
  const last = String(state.last_move_uci || '');
  const lastSquares = new Set(last.length >= 4 ? [last.slice(0, 2), last.slice(2, 4)] : []);
  const stacked = window.matchMedia('(max-width: 980px)').matches;
  const frameLimit = stacked ? 322 : 620;
  const frameWidth = Math.floor(Math.max(1, Math.min(frameLimit, window.innerWidth - 68)));
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
      <div class="chessboard" role="table" aria-label="Chess board" aria-rowcount="8" aria-colcount="8">${chunkBoard(cells, 8).map((row) => `<div class="board-row" role="row">${row.join('')}</div>`).join('')}</div>
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
  const content = piece ? `<span class="piece piece-${side}" aria-label="${escapeHtml(side)} ${escapeHtml(piece)}">${glyphs[piece] || escapeHtml(piece)}</span>` : '';
  const names = {p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king'};
  const label = piece ? `${side} ${names[piece.toLowerCase()] || piece}` : 'empty';
  return `<div class="square ${tone}${last}" role="cell" aria-label="${square}: ${escapeHtml(label)}" data-square="${square}">${content}</div>`;
}

function cellDescription(cell) {
  if (cell == null || cell === '') return 'empty';
  if (typeof cell === 'object') return Object.entries(cell).map(([key, value]) => `${key}: ${value}`).join(', ');
  const names = {X: 'X marker', O: 'O marker', B: 'black stone', W: 'white stone', R: 'red marker', Y: 'yellow marker'};
  return names[cell] || String(cell);
}

function renderGrid(event) {
  const state = event.public_state || {};
  const board = state.board || state.grid;
  if (!Array.isArray(board) || !board.length) return renderSummary(state);
  const rows = Array.isArray(board[0]) ? board : chunkBoard(board, state.rows || 3);
  const cols = Math.max(1, ...rows.map((row) => row.length));
  const cells = rows.map((row, r) => `<div class="board-row" role="row">${row.map((cell, c) => {
    const cls = cell === 'R' ? 'disc-r' : cell === 'Y' ? 'disc-y' : '';
    const content = cell == null ? '' : typeof cell === 'object' ? (cell.count ?? cellDescription(cell)) : String(cell);
    return `<div class="grid-cell ${cls}" role="cell" aria-label="Row ${r + 1}, column ${c + 1}: ${escapeHtml(cellDescription(cell))}">${escapeHtml(content)}</div>`;
  }).join('')}</div>`).join('');
  return `<div class="grid-board" role="table" aria-label="Public game board" aria-rowcount="${rows.length}" aria-colcount="${cols}" style="grid-template-columns: repeat(${cols}, minmax(0, 1fr))">${cells}</div>`;
}

function fieldName(key) { return String(key).replaceAll('_', ' '); }
function renderValue(value, depth = 0) {
  if (value == null) return '<span class="muted">Not available</span>';
  if (typeof value !== 'object') return escapeHtml(value);
  if (depth >= 5) return '<span class="muted">Nested public state</span>';
  if (Array.isArray(value)) {
    if (!value.length) return '<span class="muted">None</span>';
    const visible = value.slice(-40);
    return `${value.length > visible.length ? `<p>Showing latest ${visible.length} of ${value.length}</p>` : ''}<ol>${visible.map((item) => `<li>${renderValue(item, depth + 1)}</li>`).join('')}</ol>`;
  }
  const entries = Object.entries(value);
  if (!entries.length) return '<span class="muted">None</span>';
  return `<dl>${entries.map(([key, item]) => `<dt>${escapeHtml(fieldName(key))}</dt><dd>${renderValue(item, depth + 1)}</dd>`).join('')}</dl>`;
}
function renderSummary(state) {
  return `<section class="state-summary" aria-label="Public game state"><h2>Public state</h2>${renderValue(state)}</section>`;
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
  const outcome = event.outcome || {};
  const rows = [
    ['Move', move ? `${move.mover} -> ${labelForAction(move)}` : 'initial'],
    ['Winner', outcome.winner ?? state.winner ?? 'none'],
    ['Terminal', state.terminal_reason ?? outcome.reason ?? String(Boolean(event.terminal))],
    ['Scores', Object.entries(event.scores || {}).map(([player, score]) => `${player}: ${score}`).join(', ') || 'none'],
  ];
  if (state.fen) rows.push(['FEN', state.fen]);
  if (state.final_validation && Object.keys(state.final_validation).length) rows.push(['Validation', Object.entries(state.final_validation).map(([key, value]) => `${fieldName(key)}: ${value}`).join(', ')]);
  if (state.phase != null) rows.push(['Phase', state.phase]);
  return rows.map(([label, value]) => `<div class="detail"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>`).join('');
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
  for (const player of players) {
    const panel = document.getElementById(`panel-${player}`);
    if (panel) panel.classList.toggle('active', move?.mover === player);
    renderMoves(player);
  }
}

renderPlayerPanels();
document.getElementById('prev').addEventListener('click', () => setSelected(selected - 1));
document.getElementById('next').addEventListener('click', () => setSelected(selected + 1));
document.getElementById('play').addEventListener('click', togglePlay);
document.addEventListener('keydown', (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('input, textarea, select, [contenteditable="true"]')) return;
  if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
    event.preventDefault();
    setSelected(selected + (event.key === 'ArrowRight' ? 1 : -1));
  } else if (event.key === 'Home' || event.key === 'End') {
    event.preventDefault();
    setSelected(event.key === 'Home' ? 0 : events.length - 1);
  }
});
window.addEventListener('resize', render);
render();
</script>
</body>
</html>
"""
