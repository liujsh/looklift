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

export type LibraryRoot = { id: string; path: string };
export type LibraryItem = {
  id: string;
  path: string;
  display_name: string;
  available: boolean;
  thumbnail_path: string | null;
  file_size: number;
  modified_ns: number;
  width: number | null;
  height: number | null;
  file_format: string;
  metadata: ImageInfo;
  tags: string[];
  export_count: number;
  last_export_at: string | null;
  session_id: string | null;
  current_version_id: string | null;
  current_summary: string;
};
export type LibraryItemsPage = { items: LibraryItem[]; total: number; page: number; page_size: number };
export type LibraryFolderEntry = { name: string; path: string; count: number; cover_item_id: string | null };
export type LibraryFolderView = {
  folders: LibraryFolderEntry[];
  items: LibraryItem[];
  total: number;
  page: number;
  page_size: number;
};
export type LibraryScanTask = {
  status: "running" | "done" | "cancelled" | "error";
  message: string | null;
  result: { added: number; updated: number; missing: number } | null;
  error: string | null;
  scanned: number;
  current: string | null;
};
export type ImportSource = { id: string; name: string; path: string; kind: string };
export type ImportItem = { path: string; name: string; size: number; modified: string; format: string; fingerprint: string; duplicate: boolean };
export type ImportTask = { status: "running" | "done" | "cancelled" | "error"; message: string | null; total: number; completed: number; skipped: number; failed: { path: string; error: string }[]; paths: string[]; scan_task_id?: string };

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

export type TemplateCategory = "portrait" | "nature" | "movie" | "black_white" | "night" | "travel" | "uncategorized";

export type TemplateCard = {
  name: string;
  summary: string;
  source: "built_in" | "user";
  readonly: boolean;
  category: TemplateCategory;
  suitable_for: string[];
  principles: string[];
  steps: string[];
  key_parameters: Array<{ path: string; value: number }>;
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

export type AutomationWorkflow = {
  id: string;
  name: string;
  look_name: string;
  factor: number;
  suffix: string;
  quality: number;
  created_at: string;
};

export type AutomationPlanItem = {
  source: string;
  output: string;
  status: "ready" | "invalid" | "conflict";
  error: string | null;
};

export type AutomationPlan = {
  id: string;
  workflow: AutomationWorkflow;
  output_dir: string;
  ready: boolean;
  created_at: string;
  items: AutomationPlanItem[];
};

export type AutomationRunItem = Omit<AutomationPlanItem, "status"> & {
  status: "pending" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
};

export type AutomationRun = {
  id: string;
  plan_id: string;
  workflow: AutomationWorkflow;
  status: "running" | "done" | "cancelled" | "interrupted";
  created_at: string;
  updated_at: string;
  items: AutomationRunItem[];
  total: number;
  completed: number;
  failed: number;
  cancelled: number;
};

export type CreateAutomationWorkflowRequest = {
  name: string;
  look_name: string;
  factor: number;
  suffix: string;
  quality: number;
};

export type RuntimeSummary = {
  id: string;
  kind: "api" | "cli" | "fake";
  capabilities: string[];
  supports_resume: boolean;
  supports_mcp: boolean;
  models: string[];
  display_name: string;
  support_level: "stable" | "experimental";
  available?: boolean;
  authenticated?: boolean;
  version?: string | null;
  error?: string | null;
};

export type ProviderSettings = {
  contract_version: number;
  configured: boolean;
  provider_id?: "openai" | "ollama";
  base_url?: string;
  model?: string;
  protocol?: string;
  max_tokens?: number;
  config_version?: number;
  has_key: boolean;
};

export type PluginSummary = {
  id: string;
  version: string;
  kind: "skill" | "template" | "connector" | "provider";
  task_kind: string;
  mode: string;
  inputs: string[];
  capabilities: string[];
  granted_capabilities: string[];
  content_hash: string;
  source: string;
  enabled: boolean;
};

export type AgentRunManifest = {
  run_id: string;
  status: "starting" | "running" | "cancelling" | "interrupted" | "stale" | "completed" | "failed";
  baseline_hash: string;
  photo_hash: string;
  attempt_id: string | null;
  last_sequence: number;
  last_candidate_revision: string | null;
  stale_reason: string | null;
  runtime_id: string | null;
  provider: string | null;
  model: string | null;
  domain_pack_hash: string | null;
  session_id: string | null;
  context_sources: Array<{ id: string; version: number; hash: string; status: "used" | "omitted"; reason?: string }>;
};

export type ContextEntryType = "profile" | "rule" | "fact" | "preference" | "project" | "reference" | "feedback";

export type ContextEntryView = {
  id: string;
  type: ContextEntryType;
  content: string;
  source: string;
  scope: "global" | "project" | "run";
  name: string;
  description: string;
  confirmed: boolean;
  enabled: boolean;
  version: number;
  content_hash: string;
  created_at: string;
  updated_at: string;
};

export type ContextConfig = { enabled: boolean; auto_extract: boolean };

export type ContextTreeView = {
  schema_version: number;
  config: ContextConfig;
  entries: ContextEntryView[];
};

export type ProposalView = {
  proposal_id: string;
  target_type: "Memory" | "ProjectContext" | "Skill" | "Template" | "Reference";
  target_id: string;
  base_hash: string;
  patch: Record<string, unknown>;
  source_packet_ids: string[];
  expires_at: string;
  status: "preview" | "confirmed" | "rejected" | "applied" | "expired" | "conflict";
  applied_revision: string | null;
};
