export type CoreLegalAction = {
  actionId: string;
  kind: string;
  compact: string;
  payload: unknown;
  label: string;
  hash?: string;
};

export type CoreLegalActionView =
  | {
      include: "none";
      count: number;
      hash: string;
    }
  | {
      include: "ids";
      count: number;
      hash: string;
      ids: string[];
    }
  | {
      include: "compact" | "full";
      count: number;
      hash: string;
      actions: CoreLegalAction[];
    };

export type CoreActionOutput = {
  action: {
    action_id: string;
  };
  public_explanation: string;
};

export type ActionParseStatus =
  | { status: "incomplete" }
  | { status: "action_ready"; action: { action_id: string } }
  | { status: "explanation_delta"; text: string }
  | { status: "complete"; action: { action_id: string; payload?: unknown }; explanation: string }
  | { status: "invalid"; reason: string; code?: string };
