export type CoreReplayEvent = {
  schemaVersion: "eslams.core.replay_event.v2";
  seq: number;
  turn: number;
  type: "action_applied" | string;
  gameId: string;
  actorId: string;
  actionHash: string;
  previousStateHash: string;
  nextStateHash: string;
  timestamp: string;
  timingsMs: Record<string, unknown>;
  payload: Record<string, unknown>;
};

export type CoreReplayCheckpoint = {
  turn: number;
  seq: number;
  stateHash: string;
  snapshotR2Key?: string;
  byteOffset?: number;
};
