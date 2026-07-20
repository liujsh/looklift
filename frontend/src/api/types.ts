export type JsonObject = Record<string, unknown>;

export type BasicAnalysis = {
  temperature_shift: number;
  tint_shift: number;
  exposure: number;
  contrast: number;
  highlights: number;
  shadows: number;
  whites: number;
  blacks: number;
  texture: number;
  clarity: number;
  dehaze: number;
  vibrance: number;
  saturation: number;
};

export type ToneCurvePoint = { input: number; output: number };
export type HslEntry = {
  color: string;
  hue: number;
  saturation: number;
  luminance: number;
};
export type ColorGradingZone = { hue: number; saturation: number; luminance: number };
export type ColorGradingAnalysis = {
  shadows: ColorGradingZone;
  midtones: ColorGradingZone;
  highlights: ColorGradingZone;
  global_: ColorGradingZone;
  blending: number;
  balance: number;
};
export type EffectsAnalysis = { vignette_amount: number; grain_amount: number };

/** 与 Python ANALYSIS_SCHEMA 同构的前端唯一参数对象。 */
export type Analysis = {
  summary: string;
  steps: string[];
  basic: BasicAnalysis;
  tone_curve: ToneCurvePoint[];
  hsl: HslEntry[];
  color_grading: ColorGradingAnalysis;
  effects: EffectsAnalysis;
};

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
  analysis: JsonObject;
  factor: number;
};

export type ImageInfo = Partial<{
  iso: number;
  shutter_seconds: number;
  aperture: number;
  focal_length_mm: number;
  exposure_compensation_ev: number;
  white_balance: string;
  color_space: string;
  file_format: string;
}>;

export type ProviderConfig = {
  configured: boolean;
  provider: string;
  model: string;
  base_url: string;
  timeout: number;
  has_key: boolean;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
  status?: "done" | "failed" | "cancelled";
};

export type ChatChange = {
  path: string;
  before: unknown;
  after: unknown;
};

export type ChatStepRequest = {
  path: string;
  current_analysis: Analysis;
  factor: number;
  message: string;
  history: ChatMessage[];
  include_metadata: boolean;
};

export type ChatStepResponse = {
  analysis: Analysis;
  changes: ChatChange[];
  rejected: JsonObject[];
  explanation: string;
  limitations: string[];
  approximation: string;
  manual_steps: string[];
  done: boolean;
  provider: string;
  proxy_count: number;
  metadata_sent: boolean;
};

export type SessionMessage = Required<Pick<ChatMessage, "role" | "content">> & {
  id: string;
  provider: string | null;
  status: "done" | "failed" | "cancelled";
  created_at: string;
};

export type EditVersion = {
  id: string;
  parent_id: string | null;
  analysis: Analysis;
  source: "chat" | "manual" | "library" | "analysis" | "initial";
  summary: string;
  created_at: string;
};

export type SessionSnapshot = {
  id: string;
  image_path: string;
  created_at: string;
  updated_at: string;
  messages: SessionMessage[];
  versions: EditVersion[];
  current_version_id: string;
  current_analysis: Analysis;
};

export type SessionSummary = {
  id: string;
  display_name: string;
  updated_at: string;
  current_version_id: string;
  summary: string;
  source_available: boolean;
};

export type CreateSessionRequest = { path: string; initial_analysis: Analysis };

export type CommitSessionRequest = {
  exchange: ChatMessage[];
  analysis: Analysis;
  source: "chat" | "manual" | "library" | "analysis";
};

export type RecordSessionMessagesRequest = { exchange: ChatMessage[] };

export type LookSummary = {
  name: string;
  summary: string;
  has_preset: boolean;
  source: "built_in" | "user";
  readonly: boolean;
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
