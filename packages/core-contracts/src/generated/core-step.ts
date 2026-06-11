export type CoreContractVersion = "2.0";
export type IncludeLegalActions = "none" | "ids" | "compact" | "full";
export type ObservationView =
  | "public_compact"
  | "public_full"
  | "private_actor"
  | "ui_delta"
  | "debug";

export type CoreStateSnapshot = Record<string, unknown>;
export type CoreAction =
  | string
  | number
  | boolean
  | null
  | unknown[]
  | { actionId?: string; action_id?: string; token?: string; compact?: string; payload?: unknown };

export type CoreStepRequest = {
  coreContractVersion: CoreContractVersion;
  gameId: string;
  rulesetVersion: string;
  state: CoreStateSnapshot;
  action: CoreAction;
  actorId: string;
  requestId: string;
  turnId?: string;
  deadlineMs?: number;
  includeObservation?: boolean;
  includeLegalActions?: IncludeLegalActions;
  includeReplayEvent?: boolean;
  observationView?: ObservationView;
};

export type CoreStepTimings = {
  receivedAt: string;
  initMs?: number;
  deserializeMs?: number;
  legalActionsMs?: number;
  legalActionsAfterMs?: number;
  observationMs?: number;
  validateMs?: number;
  applyMs?: number;
  scoringMs?: number;
  serializeMs?: number;
  replayEventMs?: number;
  totalMs: number;
};

export type CoreStepError = {
  code: string;
  message: string;
  stage: string;
  recoverable: boolean;
};

export type CoreStepResponse = {
  coreVersion: string;
  coreContractVersion: CoreContractVersion;
  rulesetVersion: string;
  promptVersion: string;
  actionSchemaVersion: string;
  replaySchemaVersion: string;
  ok: boolean;
  gameId: string;
  requestId: string;
  previousStateHash: string | null;
  actionHash: string;
  nextStateHash?: string | null;
  legalActionHashBefore?: string | null;
  legalActionHashAfter?: string | null;
  state?: CoreStateSnapshot | null;
  observation?: Record<string, unknown> | null;
  legalActions?: Record<string, unknown> | null;
  replayEvent?: Record<string, unknown> | null;
  terminal?: Record<string, unknown> | null;
  error?: CoreStepError | null;
  timingsMs: CoreStepTimings;
};
