import { invoke } from "@tauri-apps/api/core";
import type {
  Analysis,
  AnalyzeRequest,
  EngineProbe,
  ExportLookRequest,
  JsonObject,
  LookSummary,
  ParamContract,
  PreviewRequest,
  SaveLookRequest,
  SidecarStatus,
  TaskResult,
} from "./types";

type FetchLike = typeof fetch;
type InvokeLike = <T>(command: string) => Promise<T>;

export class ApiError extends Error {
  constructor(message: string, readonly status: number | null = null) {
    super(message);
    this.name = "ApiError";
  }
}

export async function readSidecarStatus(invokeFn: InvokeLike = invoke): Promise<SidecarStatus> {
  return invokeFn<SidecarStatus>("sidecar_status");
}

export function clientFromStatus(status: SidecarStatus, fetchFn: FetchLike = fetch): LookliftClient {
  if (status.state !== "ready" || !status.port || !status.token) {
    throw new ApiError(status.error ?? "本地引擎尚未就绪");
  }
  return new LookliftClient(`http://127.0.0.1:${status.port}`, status.token, fetchFn);
}

export class LookliftClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchFn: FetchLike = fetch,
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

  async listLooks(): Promise<LookSummary[]> {
    const result = await this.json<{ looks: LookSummary[] }>("/api/looks");
    return result.looks;
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
