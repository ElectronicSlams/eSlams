/** Cooperative metadata has an explicit v2 schema; legacy v1 modes stay unchanged. */
export interface CooperativeTopologyV2 {
  schemaVersion: "eslams.game.topology.v2";
  mode: "cooperative";
  controlledPlayers: ["player_1", "player_2"];
  environmentPlayers: [];
  minPlayers: 2;
  maxPlayers: 2;
  defaultPlayers: 2;
  winnerRequired: false;
  drawAllowed: false;
  placementsAllowed: false;
  scoreType: "cooperative_score";
}

export interface CooperativeResultContractV2 {
  schemaVersion: "eslams.game.result.v2";
  mode: "cooperative";
  resultTypes: ["score"];
  scoreType: "cooperative_score";
  winnerRequired: false;
  drawAllowed: false;
  placementsAllowed: false;
}

export interface CooperativeResultV2 {
  schemaVersion: "eslams.game.result.v2";
  mode: "cooperative";
  terminal: true;
  winner: null;
  draw: false;
  resultType: "score";
  scores: Record<"player_1" | "player_2", number>;
  reason?: string | null;
}
