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
  _rulesetVersion = "standard",
  seed = "1",
): CoreLiteState {
  const numericSeed = Number.parseInt(seed, 10) || 1;
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

export function applyAction(state: CoreLiteState, action: unknown): CoreStepResponse {
  const previousStateHash = stateHash(state);
  const gameId = gameIdForState(state);
  const legal = getLegalActions(state);
  if (!legal.some((item) => canonicalJson(item) === canonicalJson(action))) {
    return failureResponse(gameId, previousStateHash, action, "illegal_action_for_state");
  }
  const nextState =
    gameId === "tic-tac-toe"
      ? applyTicTacToe(state, action)
      : applyConnectFour(state, action);
  return {
    coreVersion: "0.4.0",
    coreContractVersion: "2.0",
    rulesetVersion: "standard",
    promptVersion: "eslams.core.prompt.v2",
    actionSchemaVersion: "eslams.core.action_schema.v2",
    replaySchemaVersion: "eslams.core.replay_event.v2",
    ok: true,
    gameId,
    requestId: "core-lite",
    previousStateHash,
    actionHash: hashJson({ action }),
    nextStateHash: stateHash(nextState),
    legalActionHashBefore: hashJson({ legal_actions: legal.map(String) }),
    legalActionHashAfter: hashJson({ legal_actions: getLegalActions(nextState).map(String) }),
    state: nextState,
    observation: getObservation(nextState, nextState.active_player, "public_compact"),
    legalActions: {
      include: "ids",
      count: getLegalActions(nextState).length,
      hash: hashJson({ legal_actions: getLegalActions(nextState).map(String) }),
      ids: getLegalActions(nextState).map(String),
    },
    replayEvent: null,
    terminal: { terminal: nextState.terminal, outcome: nextState.outcome, scores: nextState.scores },
    error: null,
    timingsMs: { receivedAt: new Date().toISOString(), totalMs: 0 },
  };
}

export function getObservation(
  state: CoreLiteState,
  actorId: PlayerId,
  view = "public_compact",
): Record<string, unknown> {
  return {
    view,
    stateHash: stateHash(state),
    turn: state.turn,
    activePlayer: state.active_player,
    actorId,
    publicState: state.public_state,
    scores: state.scores,
    terminal: state.terminal,
    outcome: state.outcome,
    legalActionIds: getLegalActions(state).map(String),
  };
}

export function stateHash(state: CoreLiteState): string {
  const snapshot: Record<string, unknown> = { ...state };
  delete snapshot.state_hash;
  return hashJson(snapshot);
}

export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .sort()
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

function failureResponse(gameId: string, previousStateHash: string, action: unknown, code: string): CoreStepResponse {
  return {
    coreVersion: "0.4.0",
    coreContractVersion: "2.0",
    rulesetVersion: "standard",
    promptVersion: "eslams.core.prompt.v2",
    actionSchemaVersion: "eslams.core.action_schema.v2",
    replaySchemaVersion: "eslams.core.replay_event.v2",
    ok: false,
    gameId,
    requestId: "core-lite",
    previousStateHash,
    actionHash: hashJson({ action }),
    error: { code, message: code, stage: "validate", recoverable: true },
    timingsMs: { receivedAt: new Date().toISOString(), totalMs: 0 },
  };
}

function hashText(text: string): string {
  return `sha256:${sha256(text)}`;
}

function hashJson(value: unknown): string {
  return hashText(canonicalJson(value));
}

function sha256(ascii: string): string {
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
