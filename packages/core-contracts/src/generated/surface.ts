/** Surface metadata describes consumer capabilities, not deployed readiness. */
export interface GameSurfaceV1 {
  schemaVersion: "eslams.game.surface.v1";
  arena: "main_arena" | "advanced_arena" | "table_mode_pending" | "disabled";
  battlefield: "solo_benchmark" | "head_to_head" | "multi_seat" | "cooperative" | "disabled";
  benchmark: "enabled" | "disabled";
  official: "eligible" | "not_eligible" | "private_only";
  publicReason?: string | null;
}
