import type {
  BoardRecoveryDescriptor,
  BoardRecoveryEngine,
  BoardRecoveryLineage,
  BoardRecoveryPreparation,
  BoardRecoveryPublicResult,
  BoardRecoveryValidation,
} from "@eslams/core-contracts";

declare const preparation: BoardRecoveryPreparation;
declare const result: BoardRecoveryPublicResult;
declare const lineage: BoardRecoveryLineage;

const descriptor: BoardRecoveryDescriptor = preparation.descriptor;
const engine: BoardRecoveryEngine = preparation.targetEngine;
const providerCalls: 0 = preparation.newProviderCalls;
const executionEligible: false = preparation.executionEligible;
const historicalSpend: "unknown" = result.historicalSpend;
const competitiveWinner: null = result.competitiveWinner;
const scoringEligible: false = lineage.assurance.scoringEligible;

if (!result.terminal) {
  const outcome: null = result.boardOutcome;
  void outcome;
}

// @ts-expect-error Recovered positions can never be promoted to scoring eligibility.
const promoted: BoardRecoveryPublicResult = { ...result, scoringEligible: true };
// @ts-expect-error Unknown historical spend cannot be rewritten as zero.
const zeroSpend: BoardRecoveryPublicResult = { ...result, historicalSpend: 0 };
// @ts-expect-error Historical seats cannot claim routing as part of the public result.
const route = result.requestedHistoricalParticipants[0].routeKey;
// @ts-expect-error Nonterminal board outcomes are absent, not pending competitive wins.
const pendingWin: BoardRecoveryPublicResult = { ...result, terminal: false, boardOutcome: { winnerSeat: "player_1", draw: false } };

void [descriptor, engine, providerCalls, executionEligible, historicalSpend, competitiveWinner,
  scoringEligible, promoted, zeroSpend, route, pendingWin];

declare const validation: BoardRecoveryValidation;
const scope: "child_internal_source_replay" = validation.validatorScope;
const publicationReread: true = validation.publicationRequiresAuthoritativeSourceReread;
// @ts-expect-error Child-internal replay verification cannot become external custody verification.
const external: BoardRecoveryValidation = { ...validation, validatorScope: "external_custody" };
void [scope, publicationReread, external];
