// Structural types do not replace runtime validation of positive integers or
// equality between time_budget_ms and thinking.duration_ms.
export type ModelOutputPolicyV1 =
  | { mode: "provider_default" }
  | { mode: "bounded"; max_tokens: number };

export type ModelExecutionPolicyV1 = {
  schema_version: "eslams.model-execution-policy.v1";
  output: ModelOutputPolicyV1;
} & (
  | { thinking: { mode: "unbounded" } }
  | { thinking: { mode: "bounded"; duration_ms: number } }
);

export type RunnerJobRequestV2 = {
  schema_version: "eslams.runner.job.request.v2";
  job_id: string;
  arena_id: string;
  seed: number;
  agents: Record<string, Record<string, unknown>>;
  artifact_output: Record<string, unknown>;
  time_budget_ms: number | null;
  metadata: Record<string, unknown> & {
    model_execution_policy: ModelExecutionPolicyV1;
  };
  suite_context?: Record<string, unknown>;
  case_id?: string | null;
  model_id?: string | null;
  shard_index?: number | null;
  shard_count?: number | null;
  policy_ids?: string[];
};
