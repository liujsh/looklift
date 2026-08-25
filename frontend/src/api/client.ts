import { invoke } from "@tauri-apps/api/core";
import type {
  Analysis,
  AutomationPlan,
  AutomationRun,
  AutomationWorkflow,
  AnalyzeRequest,
  ChatStepRequest,
  ChatStepResponse,
  CommitSessionRequest,
  CreateSessionRequest,
  CreateAutomationWorkflowRequest,
  EngineProbe,
  ExportLookRequest,
  JsonObject,
  ImageInfo,
  LookSummary,
  TemplateCard,
  ParamContract,
  PreviewRequest,
  ProviderConfig,
  LibraryFolderView,
  LibraryItemsPage,
  LibraryRoot,
  LibraryScanTask,
  ImportSource, ImportItem, ImportTask,
  RecordSessionMessagesRequest,
  SaveLookRequest,
  SidecarStatus,
  SessionSnapshot,
  SessionSummary,
  TaskResult,
  AgentRunManifest,
  RuntimeSummary,
} from "./types";

type FetchLike = typeof fetch;
type InvokeLike = <T>(command: string) => Promise<T>;

const defaultFetch: FetchLike = (...args) => globalThis.fetch(...args);

export class ApiError extends Error {
  constructor(message: string, readonly status: number | null = null) {
    super(message);
    this.name = "ApiError";
  }
}

export async function readSidecarStatus(invokeFn: InvokeLike = invoke): Promise<SidecarStatus> {
  return invokeFn<SidecarStatus>("sidecar_status");
}

export function clientFromStatus(status: SidecarStatus, fetchFn: FetchLike = defaultFetch): LookliftClient {
  if (status.state !== "ready" || !status.port || !status.token) {
    throw new ApiError(status.error ?? "本地引擎尚未就绪");
  }
  return new LookliftClient(`http://127.0.0.1:${status.port}`, status.token, fetchFn);
}

export class LookliftClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchFn: FetchLike = defaultFetch,
  ) {}

  ping(): Promise<{ ok: boolean }> {
    return this.json("/api/ping");
  }

  engineProbe(): Promise<EngineProbe> {
    return this.json("/api/engine-probe");
  }

  paramContract(): Promise<ParamContract> {
    return this.json("/api/param-contract");
  }

  async runtimes(): Promise<RuntimeSummary[]> {
    const result = await this.json<{ runtimes: RuntimeSummary[] }>("/api/runtimes");
    return result.runtimes;
  }

  async recoverableAgentRuns(): Promise<AgentRunManifest[]> {
    const result = await this.json<{ runs: AgentRunManifest[] }>("/api/agent/runs/recoverable");
    return result.runs;
  }

  agentRun(id: string): Promise<AgentRunManifest> {
    return this.json(`/api/agent/runs/${encodeURIComponent(id)}`);
  }

  resumeAgentRun(id: string, attemptId: string, runtimeId?: string): Promise<AgentRunManifest> {
    return this.json(`/api/agent/runs/${encodeURIComponent(id)}/resume`, {
      method: "POST",
      body: JSON.stringify({ attempt_id: attemptId, runtime_id: runtimeId }),
    });
  }

  analyze(payload: AnalyzeRequest): Promise<{ task_id: string }> {
    return this.json("/api/analyze", { method: "POST", body: JSON.stringify(payload) });
  }

  task(id: string): Promise<TaskResult> {
    return this.json(`/api/tasks/${encodeURIComponent(id)}`);
  }

  preview(payload: PreviewRequest, signal?: AbortSignal): Promise<Blob> {
    return this.binary("/api/preview", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  imageInfo(path: string): Promise<ImageInfo> {
    return this.json("/api/image-info", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  }

  config(): Promise<ProviderConfig> {
    return this.json("/api/config");
  }

  saveConfig(payload: Partial<Omit<ProviderConfig, "timeout">> & { timeout?: number | string; api_key?: string }): Promise<{ ok: boolean }> {
    return this.json("/api/config", { method: "POST", body: JSON.stringify(payload) });
  }

  libraryRoots(): Promise<{ roots: LibraryRoot[] }> {
    return this.json("/api/library/roots");
  }

  addLibraryRoot(path: string): Promise<LibraryRoot> {
    return this.json("/api/library/roots", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  }

  removeLibraryRoot(id: string): Promise<{ ok: boolean }> {
    return this.json(`/api/library/roots/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  scanLibraryRoot(id: string): Promise<{ task_id: string }> {
    return this.json(`/api/library/roots/${encodeURIComponent(id)}/scan`, { method: "POST" });
  }

  libraryScan(id: string): Promise<LibraryScanTask> {
    return this.json(`/api/library/scans/${encodeURIComponent(id)}`);
  }

  cancelLibraryScan(id: string): Promise<{ ok: boolean }> {
    return this.json(`/api/library/scans/${encodeURIComponent(id)}/cancel`, { method: "POST" });
  }

  importSources(): Promise<{ sources: ImportSource[] }> { return this.json("/api/import/sources"); }
  importItems(sourceId: string, date = "", unimported = false): Promise<{ items: ImportItem[] }> {
    return this.json(`/api/import/items?source_id=${encodeURIComponent(sourceId)}&date=${encodeURIComponent(date)}&unimported=${unimported}`);
  }
  startImport(paths: string[], target?: string): Promise<{ task_id: string }> {
    return this.json("/api/import/start", { method: "POST", body: JSON.stringify({ paths, target }) });
  }
  importTask(id: string): Promise<ImportTask> { return this.json(`/api/import/tasks/${encodeURIComponent(id)}`); }
  cancelImport(id: string): Promise<{ ok: boolean }> { return this.json(`/api/import/tasks/${encodeURIComponent(id)}/cancel`, { method: "POST" }); }

  libraryItems(keyword = "", tag = "", page = 1, pageSize = 48): Promise<LibraryItemsPage> {
    return this.json(
      `/api/library/items?keyword=${encodeURIComponent(keyword)}&tag=${encodeURIComponent(tag)}&page=${page}&page_size=${pageSize}`,
    );
  }

  libraryFolder(path: string | null, page = 1, pageSize = 48): Promise<LibraryFolderView> {
    const pathQuery = path === null ? "" : `path=${encodeURIComponent(path)}&`;
    return this.json(`/api/library/folder?${pathQuery}page=${page}&page_size=${pageSize}`);
  }

  setLibraryTags(id: string, tags: string[]): Promise<{ ok: boolean }> {
    return this.json(`/api/library/items/${encodeURIComponent(id)}/tags`, {
      method: "PUT",
      body: JSON.stringify({ tags }),
    });
  }

  libraryThumbnail(id: string, signal?: AbortSignal): Promise<Blob> {
    return this.binary(`/api/library/items/${encodeURIComponent(id)}/thumbnail`, { signal });
  }

  revealLibraryItem(id: string): Promise<{ ok: boolean }> {
    return this.json(`/api/library/items/${encodeURIComponent(id)}/reveal`, { method: "POST" });
  }

  chatStep(payload: ChatStepRequest, signal?: AbortSignal): Promise<ChatStepResponse> {
    return this.json("/api/chat/step", {
      method: "POST",
      body: JSON.stringify(payload),
      signal,
    });
  }

  createSession(payload: CreateSessionRequest): Promise<SessionSnapshot> {
    return this.json("/api/sessions", { method: "POST", body: JSON.stringify(payload) });
  }

  async recentSessions(limit = 8): Promise<SessionSummary[]> {
    const result = await this.json<{ sessions: SessionSummary[] }>(`/api/sessions?limit=${limit}`);
    return result.sessions;
  }

  getSession(id: string): Promise<SessionSnapshot> {
    return this.json(`/api/sessions/${encodeURIComponent(id)}`);
  }

  sessionThumbnail(id: string, signal?: AbortSignal): Promise<Blob> {
    return this.binary(`/api/sessions/${encodeURIComponent(id)}/thumbnail`, { signal });
  }

  commitSession(id: string, payload: CommitSessionRequest): Promise<SessionSnapshot> {
    return this.json(`/api/sessions/${encodeURIComponent(id)}/commit`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  recordSessionMessages(
    id: string,
    payload: RecordSessionMessagesRequest,
  ): Promise<SessionSnapshot> {
    return this.json(`/api/sessions/${encodeURIComponent(id)}/messages`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  upload(file: File): Promise<{ path: string }> {
    const form = new FormData();
    form.set("file", file, file.name);
    return this.json("/api/upload", { method: "POST", body: form });
  }

  async listLooks(): Promise<LookSummary[]> {
    const result = await this.json<{ looks: LookSummary[] }>("/api/looks");
    return result.looks;
  }

  async listTemplates(): Promise<TemplateCard[]> {
    const result = await this.json<{ templates: TemplateCard[] }>("/api/templates");
    return result.templates;
  }

  getLook(name: string): Promise<Analysis> {
    return this.json(`/api/looks/${encodeURIComponent(name)}`);
  }

  saveLook(payload: SaveLookRequest): Promise<{ name: string }> {
    return this.json("/api/looks", { method: "POST", body: JSON.stringify(payload) });
  }

  exportLook(name: string, payload: ExportLookRequest = {}): Promise<JsonObject> {
    return this.json(`/api/looks/${encodeURIComponent(name)}/export`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  report(name: string): Promise<string> {
    return this.text(`/report/${encodeURIComponent(name)}`, undefined, false);
  }

  reportUrl(name: string): string {
    return `${this.baseUrl}/report/${encodeURIComponent(name)}`;
  }

  async listAutomationWorkflows(): Promise<AutomationWorkflow[]> {
    const result = await this.json<{ workflows: AutomationWorkflow[] }>("/api/automation/workflows");
    return result.workflows;
  }

  createAutomationWorkflow(payload: CreateAutomationWorkflowRequest): Promise<AutomationWorkflow> {
    return this.json("/api/automation/workflows", { method: "POST", body: JSON.stringify(payload) });
  }

  deleteAutomationWorkflow(id: string): Promise<{ ok: boolean }> {
    return this.json(`/api/automation/workflows/${encodeURIComponent(id)}`, { method: "DELETE" });
  }

  planAutomation(payload: { workflow_id: string; inputs: string[]; output_dir: string }): Promise<AutomationPlan> {
    return this.json("/api/automation/plans", { method: "POST", body: JSON.stringify(payload) });
  }

  startAutomationRun(planId: string): Promise<{ run_id: string }> {
    return this.json("/api/automation/runs", {
      method: "POST",
      body: JSON.stringify({ plan_id: planId }),
    });
  }

  async listAutomationRuns(): Promise<AutomationRun[]> {
    const result = await this.json<{ runs: AutomationRun[] }>("/api/automation/runs");
    return result.runs;
  }

  automationRun(id: string): Promise<AutomationRun> {
    return this.json(`/api/automation/runs/${encodeURIComponent(id)}`);
  }

  cancelAutomationRun(id: string): Promise<{ ok: boolean }> {
    return this.json(`/api/automation/runs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
  }

  retryAutomationRun(id: string): Promise<{ run_id: string }> {
    return this.json(`/api/automation/runs/${encodeURIComponent(id)}/retry`, { method: "POST" });
  }

  private async request(
    path: string,
    init: RequestInit = {},
    authenticated = true,
  ): Promise<Response> {
    const headers = new Headers(init.headers);
    if (authenticated) headers.set("X-Looklift-Token", this.token);
    if (init.body !== undefined && !(init.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    try {
      const response = await this.fetchFn(`${this.baseUrl}${path}`, { ...init, headers });
      if (!response.ok) throw await this.responseError(response);
      return response;
    } catch (reason) {
      if (reason instanceof ApiError || (reason instanceof DOMException && reason.name === "AbortError")) {
        throw reason;
      }
      throw new ApiError(`无法连接本地引擎：${String(reason)}`);
    }
  }

  private async responseError(response: Response): Promise<ApiError> {
    try {
      const payload = (await response.clone().json()) as { error?: unknown };
      if (typeof payload.error === "string" && payload.error) {
        return new ApiError(payload.error, response.status);
      }
    } catch {
      // 非 JSON 错误由下面的稳定中文文案兜底。
    }
    return new ApiError(`本地引擎请求失败（HTTP ${response.status}）`, response.status);
  }

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    return (await this.request(path, init)).json() as Promise<T>;
  }

  private async binary(path: string, init?: RequestInit): Promise<Blob> {
    return (await this.request(path, init)).blob();
  }

  private async text(path: string, init?: RequestInit, authenticated = true): Promise<string> {
    return (await this.request(path, init, authenticated)).text();
  }
}
