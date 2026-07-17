export type JsonObject = Record<string, unknown>;
export type Analysis = JsonObject;

export type SidecarStatus = {
  state: "starting" | "ready" | "error" | "stopping";
  port: number | null;
  token: string | null;
  details: JsonObject | null;
  error: string | null;
};

export type EngineProbe = {
  rendered: boolean;
  numba: string;
  pyvips?: string;
  libvips: string;
};

export type ParamRule = {
  min: number;
  max: number;
  default: number;
};

export type ParamContract = Record<string, ParamRule>;

export type AnalyzeRequest = {
  path: string;
  original?: string;
  hint?: string;
  backend?: string;
};

export type PreviewRequest = {
  path: string;
  analysis: Analysis;
  factor: number;
};

export type LookSummary = {
  name: string;
  summary: string;
  has_preset: boolean;
};

export type SaveLookRequest = {
  name: string;
  analysis: Analysis;
  factor?: number;
};

export type ExportLookRequest = {
  factor?: number;
  sidecar?: string;
};

export type TaskResult = {
  status: "running" | "done" | "error";
  message: string | null;
  result: JsonObject | null;
  error: string | null;
};
