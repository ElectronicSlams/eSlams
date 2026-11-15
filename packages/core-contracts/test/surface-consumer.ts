import type { GameSurfaceV1 } from "../src/generated/index.js";

const hanabi: GameSurfaceV1 = {
  schemaVersion: "eslams.game.surface.v1",
  arena: "advanced_arena",
  battlefield: "cooperative",
  benchmark: "disabled",
  official: "not_eligible",
};
const historicalDisabled: GameSurfaceV1 = { ...hanabi, battlefield: "disabled" };
// @ts-expect-error Unknown Battlefield modes must not type-check.
const unsupported: GameSurfaceV1 = { ...hanabi, battlefield: "unknown" };
void [hanabi, historicalDisabled, unsupported];
