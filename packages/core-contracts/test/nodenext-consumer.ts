import type {
  CoreStepRequest,
  ProviderAttemptV2,
  RunIntegrityV2,
} from "@eslams/core-contracts";

type ConsumerContract = {
  request: CoreStepRequest;
  attempt: ProviderAttemptV2;
  integrity: RunIntegrityV2;
};

export type { ConsumerContract };
