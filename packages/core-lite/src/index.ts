import type { CoreStepResponse } from "@eslams/core-contracts";

type PlayerId = "player_1" | "player_2";
type Cell = string | null;

export type CoreLiteState = {
  state_id: string;
  state_hash?: string;
  turn: number;
  active_player: PlayerId;
  public_state: Record<string, unknown>;
  private_state_by_player: Record<PlayerId, Record<string, unknown>>;
  legal_actions_by_player: Record<PlayerId, unknown[]>;
  scores: Record<PlayerId, number>;
  terminal: boolean;
  outcome: Record<string, unknown> | null;
  rng_commitment: string;
  render_hints: Record<string, unknown>;
  metadata: Record<string, unknown>;
};

export function createInitialState(
  gameId: string,
  rulesetVersion = "standard",
  seed = "1",
): CoreLiteState {
  if (rulesetVersion !== "standard") throw new Error("Core-lite supports the standard ruleset only");
  if (!/^[+-]?\d+$/.test(seed)) throw new Error("seed must be a decimal integer");
  const numericSeed = Number(seed);
  if (!Number.isSafeInteger(numericSeed)) throw new Error("seed must be a safe integer");
  if (gameId === "tic-tac-toe") {
    return ticTacToeState(Array(9).fill(null), 0, "player_1", numericSeed, null);
  }
  if (gameId === "connect-four") {
    const board = Array.from({ length: 6 }, () => Array(7).fill(null));
    return connectFourState(board, 0, "player_1", numericSeed, null);
  }
  throw new Error(`unsupported Core-lite game ${gameId}`);
}

export function getLegalActions(state: CoreLiteState): unknown[] {
  return state.legal_actions_by_player[state.active_player] ?? [];
}

export function applyAction(input: unknown, action: unknown): CoreStepResponse {
  let previousStateHash: string | null = null;
  let gameId = "";
  let legalHashBefore: string | null = null;
  try {
    const state = validatedState(input);
    gameId = gameIdForState(state);
    previousStateHash = stateHash(state);
    if (state.state_hash && state.state_hash !== previousStateHash) {
      throw new Error("state_hash does not match canonical state");
    }
    if (state.terminal) {
      return failureResponse(gameId, previousStateHash, action, "terminal_state", false);
    }
    const legal = getLegalActions(state);
    legalHashBefore = hashJson({ legal_actions: legal.map(String) });
    const rawAction = resolveAction(action, legal);
    if (!legal.some((item) => item === rawAction)) {
      const code = typeof rawAction === "string" ? "unknown_action_id" : "illegal_action_for_state";
      return failureResponse(gameId, previousStateHash, action, code, true, legalHashBefore);
    }
    const nextState = gameId === "tic-tac-toe"
      ? applyTicTacToe(state, rawAction) : applyConnectFour(state, rawAction);
    const nextStateHash = stateHash(nextState);
    const nextLegal = getLegalActions(nextState).map(String);
    const timingsMs = { receivedAt: new Date().toISOString(), totalMs: 0 };
    return {
      ...responseVersions(),
      ok: true,
      gameId,
      requestId: "core-lite",
      previousStateHash,
      actionHash: hashJson({ action: actionPayload(gameId, rawAction as number) }),
      nextStateHash,
      legalActionHashBefore: legalHashBefore,
      legalActionHashAfter: hashJson({ legal_actions: nextLegal }),
      state: nextState,
      observation: getObservation(nextState, nextState.active_player, "public_compact"),
      legalActions: {
        include: "ids", count: nextLegal.length,
        hash: hashJson({ legal_actions: nextLegal }), ids: nextLegal,
      },
      replayEvent: {
        schemaVersion: "eslams.core.replay_event.v2", seq: state.turn, turn: state.turn,
        type: "action_applied", gameId, actorId: state.active_player,
        actionHash: hashJson({ action: rawAction }), previousStateHash, nextStateHash,
        timestamp: new Date().toISOString(), timingsMs, payload: { action: rawAction },
      },
      terminal: { terminal: nextState.terminal, outcome: nextState.outcome, scores: nextState.scores },
      error: null,
      timingsMs,
    };
  } catch {
    // Malformed/untrusted snapshots must never leak a raw runtime exception.
    return failureResponse(gameId, previousStateHash, action, "transition_error", false,
      legalHashBefore, "unknown");
  }
}

function responseVersions() {
  return {
    coreVersion: "0.6.1", coreContractVersion: "2.0" as const, rulesetVersion: "standard",
    promptVersion: "eslams.core.prompt.v2", actionSchemaVersion: "eslams.core.action_schema.v2",
    replaySchemaVersion: "eslams.core.replay_event.v2",
  };
}

function resolveAction(action: unknown, legal: unknown[]): unknown {
  if (isRecord(action)) {
    const id = action.actionId || action.action_id || action.token;
    if (typeof id === "string") return resolveAction(id, legal);
    if ("payload" in action) return resolveAction(action.payload, legal);
    if ("compact" in action) return resolveAction(action.compact, legal);
  }
  if (typeof action === "string") return legal.find((item) => String(item) === action) ?? action;
  return action;
}

function actionPayload(gameId: string, action: number) {
  const positions = ["top-left", "top", "top-right", "left", "center", "right",
    "bottom-left", "bottom", "bottom-right"];
  return {
    actionId: String(action), compact: String(action), payload: action,
    kind: gameId === "tic-tac-toe" ? "mark_square" : "drop_disc",
    label: gameId === "tic-tac-toe" ? `Play ${positions[action]}` : `Drop in column ${action + 1}`,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function validatedState(input: unknown): CoreLiteState {
  if (!isRecord(input) || !isRecord(input.public_state) || !isRecord(input.metadata)
    || !isRecord(input.private_state_by_player) || !isRecord(input.legal_actions_by_player)
    || !isRecord(input.scores) || !isRecord(input.render_hints)
    || typeof input.state_id !== "string" || !input.state_id
    || typeof input.rng_commitment !== "string"
    || !Number.isSafeInteger(input.turn) || (input.turn as number) < 0
    || !Number.isSafeInteger(input.metadata.seed)
    || !["player_1", "player_2"].includes(input.active_player as string)
    || typeof input.terminal !== "boolean"
    || (input.outcome !== null && !isRecord(input.outcome))) {
    throw new Error("invalid Core-lite snapshot");
  }
  const state = input as CoreLiteState;
  const gameId = gameIdForState(state);
  const board = state.public_state.board;
  const validCells = gameId === "tic-tac-toe" ? [null, "X", "O"] : [null, "R", "Y"];
  const validRow = (row: unknown, size: number) => Array.isArray(row)
    && row.length === size && row.every((cell) => validCells.includes(cell));
  if (gameId === "tic-tac-toe" ? !validRow(board, 9)
    : !Array.isArray(board) || board.length !== 6 || !board.every((row) => validRow(row, 7))) {
    throw new Error("invalid Core-lite board");
  }
  for (const player of ["player_1", "player_2"] as const) {
    const legal = state.legal_actions_by_player[player];
    if (!isRecord(state.private_state_by_player[player]) || !Array.isArray(legal)
      || !legal.every((move) => Number.isInteger(move) && (move as number) >= 0
        && (move as number) < (gameId === "tic-tac-toe" ? 9 : 7))
      || typeof state.scores[player] !== "number" || !Number.isFinite(state.scores[player])) {
      throw new Error("invalid Core-lite player data");
    }
  }
  return state;
}

export function getObservation(
  state: CoreLiteState,
  actorId: PlayerId,
  view = "public_compact",
): Record<string, unknown> {
  if (view === "ui_delta") return {
    view, stateHash: stateHash(state), turn: state.turn, activePlayer: state.active_player,
    terminal: state.terminal, outcome: state.outcome,
  };
  if (view === "debug") return { view, state, legalActionIds: state.legal_actions_by_player[actorId].map(String) };
  const full = view === "public_full" || view === "private_actor";
  const gameId = gameIdForState(state);
  const actorLegal = state.legal_actions_by_player[actorId];
  const observation = gameId === "tic-tac-toe"
    ? { board: state.public_state.board, you_are: actorId,
        mark: actorId === "player_1" ? "X" : "O", legal_squares: actorLegal }
    : { board: state.public_state.board, you_are: actorId,
        disc: actorId === "player_1" ? "R" : "Y", legal_columns: actorLegal, scores: state.scores };
  return {
    view,
    stateHash: stateHash(state),
    observationHash: hashJson({ observation: state.public_state }),
    ...(full ? { observation } : {}),
    turn: state.turn,
    activePlayer: state.active_player,
    actorId,
    publicState: state.public_state,
    scores: state.scores,
    terminal: state.terminal,
    outcome: state.outcome,
    legalActionIds: actorLegal.map(String),
  };
}

const STATE_KEYS = ["state_id", "turn", "active_player", "public_state",
  "private_state_by_player", "legal_actions_by_player", "scores", "terminal", "outcome",
  "rng_commitment", "render_hints", "metadata"];

export function stateHash(state: CoreLiteState): string {
  // Python ArenaState hashes exactly these fields and serializes scores as floats.
  const fields = STATE_KEYS.slice().sort().map((key) => {
    const value = state[key as keyof CoreLiteState];
    const encoded = key === "scores" ? `{${Object.keys(state.scores).sort().map((player) => {
      const score = state.scores[player as PlayerId];
      if (!Number.isFinite(score)) throw new Error("score must be finite");
      return `${JSON.stringify(player)}:${Number.isInteger(score) ? `${score}.0` : String(score)}`;
    }).join(",")}}` : canonicalJson(value);
    return `${JSON.stringify(key)}:${encoded}`;
  });
  return hashText(`{${fields.join(",")}}`);
}

function compareJsonKeys(left: string, right: string): number {
  // Python compares Unicode scalar values; JavaScript's default sort uses UTF-16.
  const a = Array.from(left, (char) => char.codePointAt(0)!);
  const b = Array.from(right, (char) => char.codePointAt(0)!);
  for (let index = 0; index < Math.min(a.length, b.length); index += 1) {
    if (a[index] !== b[index]) return a[index] - b[index];
  }
  return a.length - b.length;
}

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    const encoded = JSON.stringify(value);
    if (encoded === undefined || (typeof value === "number" && !Number.isFinite(value))) {
      throw new Error("value must be finite JSON");
    }
    return encoded;
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort(compareJsonKeys)
    .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
    .join(",")}}`;
}

function applyTicTacToe(state: CoreLiteState, action: unknown): CoreLiteState {
  if (typeof action !== "number") throw new Error("tic-tac-toe action must be a number");
  const board = [...(state.public_state.board as Cell[])];
  board[action] = state.active_player === "player_1" ? "X" : "O";
  const winner = ticTacToeWinner(board);
  const outcome = winner ? { winner: state.active_player, reason: "three_in_a_row" } : null;
  const next = state.active_player === "player_1" ? "player_2" : "player_1";
  return ticTacToeState(board, state.turn + 1, next, Number(state.metadata.seed), outcome);
}

function applyConnectFour(state: CoreLiteState, action: unknown): CoreLiteState {
  if (typeof action !== "number") throw new Error("connect-four action must be a number");
  const board = (state.public_state.board as Cell[][]).map((row) => [...row]);
  const disc = state.active_player === "player_1" ? "R" : "Y";
  for (let row = 5; row >= 0; row -= 1) {
    if (board[row][action] === null) {
      board[row][action] = disc;
      break;
    }
  }
  const outcome = connectFourWinner(board, disc)
    ? { winner: state.active_player, reason: "four_in_a_row" }
    : null;
  const next = state.active_player === "player_1" ? "player_2" : "player_1";
  return connectFourState(board, state.turn + 1, next, Number(state.metadata.seed), outcome);
}

function ticTacToeState(
  board: Cell[],
  turn: number,
  active: PlayerId,
  seed: number,
  outcome: Record<string, unknown> | null,
): CoreLiteState {
  const terminal = outcome !== null || turn >= 9 || board.every((cell) => cell !== null);
  const resolvedOutcome = outcome ?? (terminal ? { winner: null, reason: "draw" } : null);
  const scores = scoresForOutcome(resolvedOutcome);
  const legal = terminal ? [] : board.flatMap((cell, index) => (cell === null ? [index] : []));
  return finalizeState({
    state_id: `state_${String(turn).padStart(6, "0")}`,
    turn,
    active_player: active,
    public_state: { board, rows: 3, cols: 3 },
    private_state_by_player: { player_1: {}, player_2: {} },
    legal_actions_by_player: {
      player_1: active === "player_1" ? legal : [],
      player_2: active === "player_2" ? legal : [],
    },
    scores,
    terminal,
    outcome: resolvedOutcome,
    rng_commitment: hashText(`tic-tac-toe:${seed}`),
    render_hints: { renderer: "grid", symbols: { player_1: "X", player_2: "O" } },
    metadata: { seed },
  });
}

function connectFourState(
  board: Cell[][],
  turn: number,
  active: PlayerId,
  seed: number,
  outcome: Record<string, unknown> | null,
): CoreLiteState {
  const terminal = outcome !== null || turn >= 42 || board[0].every((cell) => cell !== null);
  const resolvedOutcome = outcome ?? (terminal ? { winner: null, reason: "draw" } : null);
  const scores = scoresForOutcome(resolvedOutcome);
  const legal = terminal ? [] : board[0].flatMap((cell, col) => (cell === null ? [col] : []));
  return finalizeState({
    state_id: `state_${String(turn).padStart(6, "0")}`,
    turn,
    active_player: active,
    public_state: { board, rows: 6, cols: 7 },
    private_state_by_player: { player_1: {}, player_2: {} },
    legal_actions_by_player: {
      player_1: active === "player_1" ? legal : [],
      player_2: active === "player_2" ? legal : [],
    },
    scores,
    terminal,
    outcome: resolvedOutcome,
    rng_commitment: hashText(`connect-four:${seed}`),
    render_hints: { renderer: "grid", symbols: { player_1: "R", player_2: "Y" } },
    metadata: { seed },
  });
}

function finalizeState(state: Omit<CoreLiteState, "state_hash">): CoreLiteState {
  const withHash = state as CoreLiteState;
  withHash.state_hash = stateHash(withHash);
  return withHash;
}

function scoresForOutcome(outcome: Record<string, unknown> | null): Record<PlayerId, number> {
  if (!outcome) return { player_1: 0, player_2: 0 };
  if (outcome.winner === null) return { player_1: 0.5, player_2: 0.5 };
  return outcome.winner === "player_1" ? { player_1: 1, player_2: 0 } : { player_1: 0, player_2: 1 };
}

function ticTacToeWinner(board: Cell[]): string | null {
  const lines = [
    [0, 1, 2],
    [3, 4, 5],
    [6, 7, 8],
    [0, 3, 6],
    [1, 4, 7],
    [2, 5, 8],
    [0, 4, 8],
    [2, 4, 6],
  ];
  for (const [a, b, c] of lines) {
    if (board[a] && board[a] === board[b] && board[a] === board[c]) return board[a];
  }
  return null;
}

function connectFourWinner(board: Cell[][], disc: string): boolean {
  const directions = [
    [1, 0],
    [0, 1],
    [1, 1],
    [1, -1],
  ];
  for (let row = 0; row < 6; row += 1) {
    for (let col = 0; col < 7; col += 1) {
      for (const [dr, dc] of directions) {
        let ok = true;
        for (let i = 0; i < 4; i += 1) {
          const r = row + dr * i;
          const c = col + dc * i;
          ok = ok && r >= 0 && r < 6 && c >= 0 && c < 7 && board[r][c] === disc;
        }
        if (ok) return true;
      }
    }
  }
  return false;
}

function gameIdForState(state: CoreLiteState): string {
  const rows = state.public_state.rows;
  const cols = state.public_state.cols;
  if (rows === 3 && cols === 3) return "tic-tac-toe";
  if (rows === 6 && cols === 7) return "connect-four";
  throw new Error("unknown Core-lite state shape");
}

function failureResponse(gameId: string, previousStateHash: string | null, action: unknown,
  code: string, recoverable: boolean, legalHashBefore: string | null = null,
  stage = "validate"): CoreStepResponse {
  let actionHash: string;
  try { actionHash = hashJson({ action }); } catch { actionHash = hashJson({ action: null }); }
  return {
    ...responseVersions(), ok: false, gameId, requestId: "core-lite", previousStateHash, actionHash,
    nextStateHash: null, legalActionHashBefore: legalHashBefore, legalActionHashAfter: null,
    state: null, observation: null, legalActions: null, replayEvent: null, terminal: null,
    error: { code, message: code, stage, recoverable },
    timingsMs: { receivedAt: new Date().toISOString(), totalMs: 0 },
  };
}

function hashText(text: string): string {
  return `sha256:${sha256(text)}`;
}

function hashJson(value: unknown): string {
  return hashText(canonicalJson(value));
}

function sha256(text: string): string {
  // SHA-256 consumes UTF-8 bytes, not JavaScript UTF-16 code units.
  let ascii = Array.from(new TextEncoder().encode(text), (byte) => String.fromCharCode(byte)).join("");
  const rightRotate = (value: number, amount: number) => (value >>> amount) | (value << (32 - amount));
  const mathPow = Math.pow;
  const maxWord = mathPow(2, 32);
  const words: number[] = [];
  const asciiBitLength = ascii.length * 8;
  let hash: number[] = [];
  let k: number[] = [];
  let primeCounter = 0;
  let candidate = 2;
  const isComposite: Record<number, boolean> = {};
  while (primeCounter < 64) {
    if (!isComposite[candidate]) {
      for (let i = 0; i < 313; i += candidate) isComposite[i] = true;
      hash[primeCounter] = (mathPow(candidate, 0.5) * maxWord) | 0;
      k[primeCounter] = (mathPow(candidate, 1 / 3) * maxWord) | 0;
      primeCounter += 1;
    }
    candidate += 1;
  }
  ascii += "\x80";
  while ((ascii.length % 64) - 56) ascii += "\x00";
  for (let i = 0; i < ascii.length; i += 1) {
    words[i >> 2] |= ascii.charCodeAt(i) << (((3 - i) % 4) * 8);
  }
  words[words.length] = (asciiBitLength / maxWord) | 0;
  words[words.length] = asciiBitLength;
  for (let j = 0; j < words.length; ) {
    const w = words.slice(j, (j += 16));
    const oldHash = [...hash];
    for (let i = 0; i < 64; i += 1) {
      const w15 = w[i - 15];
      const w2 = w[i - 2];
      const a = hash[0];
      const e = hash[4];
      const temp1 =
        hash[7] +
        (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)) +
        ((e & hash[5]) ^ (~e & hash[6])) +
        k[i] +
        (w[i] =
          i < 16
            ? w[i]
            : (w[i - 16] +
                (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3)) +
                w[i - 7] +
                (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10))) |
              0);
      const temp2 =
        (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)) +
        ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
      hash = [(temp1 + temp2) | 0, hash[0], hash[1], hash[2], (hash[3] + temp1) | 0, hash[4], hash[5], hash[6]];
    }
    for (let i = 0; i < 8; i += 1) hash[i] = (hash[i] + oldHash[i]) | 0;
  }
  return hash.map((value) => (value >>> 0).toString(16).padStart(8, "0")).join("");
}
