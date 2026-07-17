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
