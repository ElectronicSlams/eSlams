export type PromptRole = "system" | "developer";

export type GamePromptPackage = {
  gameId: string;
  rulesetVersion: string;
  promptVersion: string;
  stablePrefix: {
    role: PromptRole;
    content: string;
    cacheRecommended: boolean;
  }[];
  dynamicTurn: {
    moveHistory: string;
    currentObservation: string;
    legalActions: string;
  };
  outputSchema: Record<string, unknown>;
  parserVersion: string;
  promptHash: string;
  tokenEstimate: number;
};
