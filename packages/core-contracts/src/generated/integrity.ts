export type FailureClass =
  | "provider_transport_error"
  | "provider_request_rejected"
  | "provider_response_schema_mismatch"
  | "action_response_unparseable"
  | "action_not_legal"
  | "arena_apply_error"
  | "provider_auth_failed"
  | "provider_permission_failed"
  | "provider_rate_limited"
  | "provider_timeout"
  | "provider_unavailable";

export type ActionProvenance =
  | "provider_action"
  | "local_action"
  | "fallback_action";

export type ProviderAttemptKind =
  | "primary"
  | "case_retry"
  | "action_repair"
  | "canary";

export type ProviderOutcome =
  | "ok"
  | FailureClass
  | "no_action"
  | "gateway_auth_failed"
  | "unavailable";

export interface ProviderReceiptV2 {
  schema_version: "eslams.provider.receipt.v2";
  provider: string;
  model: string;
  environment: string;
  physical_run_id: string;
  run_id: string;
  official_run_id: string;
  model_lane_id: string;
  run_job_id: string;
  episode_id?: string | null;
  case_id: string | null;
  locked_model_id: string | null;
  model_identity_source: string | null;
  endpoint_kind: string | null;
  parser_version: string | null;
  outcome: ProviderOutcome;
  agent_id: string;
  agent_version?: string | null;
  turn_id: number;
  case_attempt_index: number;
  shard_index: number | null;
  event_id: string | null;
  logical_action_id: string | null;
  active_player?: string | null;
  seat_id?: string | null;
  attempt: number;
  attempt_index?: number;
  attempt_kind: ProviderAttemptKind;
  status: "started" | "completed" | "failed";
  action_applied: boolean;
  case_valid_for_scoring: boolean;
  usage: Record<string, unknown>;
  usage_unavailable_reason: string | null;
  pricing: Record<string, unknown>;
  estimated_cost: Record<string, unknown>;
  rate_card_id: string | null;
  rate_card_reference: PriceCardReferenceV1 | null;
  reasoning_included_in_output: boolean | null;
  usage_source: string | null;
  usage_complete: boolean;
  cost_source: string | null;
  cost_complete: boolean;
  wire_parse_status: "ok" | "failed" | "not_attempted";
  action_parse_status: "ok" | "failed" | "not_attempted";
}

export interface PriceCardReferenceV1 {
  schemaVersion: "eslams.price-card-reference.v1";
  rateCardId: string;
  rateCardHash: `sha256:${string}`;
  provider: string;
  model: string;
  currency: "USD";
  sourceUri: string;
  effectiveAt: string | null;
  retrievedAt: string | null;
  complete: true;
}

export interface RunIntegrityV2 {
  schemaVersion: "eslams.run-integrity.v2";
  integrityStatus: "valid" | "invalid" | "incomplete";
  validForScoring: boolean;
  invalidReasonCodes: string[];
  agentErrorCountByPlayer: Record<string, number>;
  fallbackActionCountByPlayer: Record<string, number>;
  illegalActionCountByPlayer: Record<string, number>;
  providerStatusByPlayer: Record<string, string>;
  providerActionCountByPlayer: Record<string, number>;
  logicalActionCountByPlayer: Record<string, number>;
  usageComplete: boolean;
  costComplete: boolean;
  modelIdentityVerified: boolean;
  attemptLedgerComplete: boolean;
}

export interface ProviderAttemptV2 {
  schemaVersion: "eslams.provider-attempt.v2";
  eventId: string;
  environment: string;
  physicalRunId: string;
  officialRunId: string;
  modelLaneId: string;
  runJobId: string;
  shardIndex: number;
  caseId: string | null;
  caseAttemptIndex: number;
  turnIndex: number;
  seatId: string;
  logicalActionId: string;
  attemptIndex: number;
  attemptKind: ProviderAttemptKind;
  parentAttemptId: string | null;
  provider: string;
  requestedModel: string;
  resolvedModel: string | null;
  modelIdentitySource: "provider_response" | "pinned_endpoint" | null;
  providerEndpoint: string;
  endpointKind: string | null;
  parserVersion: string | null;
  wrapperVersion: string | null;
  status: "started" | "completed" | "failed";
  gatewayRequestId: string | null;
  providerRequestId: string | null;
  httpStatus: number | null;
  errorClass: FailureClass | null;
  requestStartedAt: string;
  requestCompletedAt: string | null;
  latencyMs: number | null;
  inputTokens: number | null;
  cachedInputTokens: number | null;
  outputTokens: number | null;
  reasoningTokens: number | null;
  totalTokens: number | null;
  reasoningIncludedInOutput: boolean | null;
  usageSource: string | null;
  usageComplete: boolean;
  estimatedCostUsd: number | null;
  costSource: string | null;
  costComplete: boolean;
  rateCardId: string | null;
  wireParseStatus: string | null;
  actionParseStatus: string | null;
  actionApplied: boolean;
  caseValidForScoring: boolean;
}

export interface UsageSummaryV2 {
  schemaVersion: "eslams.usage-summary.v2";
  totalInputTokens: number | null;
  totalOutputTokens: number | null;
  totalCachedInputTokens: number | null;
  totalReasoningTokens: number | null;
  totalTokens: number | null;
  totalCostUsd: number | null;
  usageComplete: boolean;
  costComplete: boolean;
  receiptCount: number;
  attemptCount: number;
  logicalActionCount: number;
  attemptLedgerComplete: boolean;
  unavailableReasonCodes: string[];
  rateCardReferences: string[];
  bySeat: Record<string, unknown>;
  byProvider: Record<string, unknown>;
  byModel: Record<string, unknown>;
  byAttemptKind: Record<string, unknown>;
  byStatus: Record<string, unknown>;
}
