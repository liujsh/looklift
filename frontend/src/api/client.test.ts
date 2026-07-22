import { describe, expect, it, vi } from "vitest";
import { LookliftClient, clientFromStatus, readSidecarStatus } from "./client";
import type { Analysis, SidecarStatus } from "./types";

type RecordedRequest = { url: string; init: RequestInit };

function responseQueue(responses: Response[]) {
  const requests: RecordedRequest[] = [];
  const fetchFn = async (input: RequestInfo | URL, init: RequestInit = {}) => {
    requests.push({ url: String(input), init });
    const response = responses.shift();
    if (!response) throw new Error("测试响应队列已耗尽");
    return response;
  };
  return { fetchFn: fetchFn as typeof fetch, requests };
}

function readyStatus(): SidecarStatus {
  return {
    state: "ready",
    port: 43123,
    token: "secret-token",
    details: { event: "ready" },
    error: null,
  };
}

describe("LookliftClient", () => {
  it("用 Window 接收者调用 WebView 原生 fetch", async () => {
    const nativeFetch = vi.fn(function (this: unknown) {
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(Response.json({ ok: true }));
    });
    vi.stubGlobal("fetch", nativeFetch);
    try {
      const client = clientFromStatus(readyStatus());

      await expect(client.ping()).resolves.toEqual({ ok: true });
      expect(nativeFetch.mock.contexts[0]).toBe(globalThis);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("从 Tauri 状态命令取得连接信息", async () => {
    const commands: string[] = [];
    const status = await readSidecarStatus(async <T>(command: string) => {
      commands.push(command);
      return readyStatus() as T;
    });

    expect(commands).toEqual(["sidecar_status"]);
    expect(status.port).toBe(43123);
    expect(() => clientFromStatus({ ...status, state: "starting" })).toThrow("本地引擎尚未就绪");
  });

  it("为 JSON 请求添加启动令牌和内容类型", async () => {
    const queue = responseQueue([
      Response.json({ task_id: "task-1" }),
      Response.json({ ok: true }),
    ]);
    const client = clientFromStatus(readyStatus(), queue.fetchFn);

    await client.analyze({ path: "C:/照片/a.jpg", hint: "暖色" });
    await client.ping();

    expect(queue.requests[0].url).toBe("http://127.0.0.1:43123/api/analyze");
    const postHeaders = new Headers(queue.requests[0].init.headers);
    expect(postHeaders.get("X-Looklift-Token")).toBe("secret-token");
    expect(postHeaders.get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(queue.requests[0].init.body))).toEqual({ path: "C:/照片/a.jpg", hint: "暖色" });
    const getHeaders = new Headers(queue.requests[1].init.headers);
    expect(getHeaders.get("X-Looklift-Token")).toBe("secret-token");
    expect(getHeaders.has("Content-Type")).toBe(false);
  });

  it("分别解析参数契约、图库列表和 JPEG 二进制预览", async () => {
    const contract = { "basic.exposure": { min: -5, max: 5, default: 0 } };
    const looks = [{ name: "胶片", summary: "柔和低反差", has_preset: true }];
    const jpeg = new Uint8Array([0xff, 0xd8, 0xff, 0xd9]);
    const queue = responseQueue([
      Response.json(contract),
      Response.json({ looks }),
      new Response(jpeg, { headers: { "Content-Type": "image/jpeg" } }),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    await expect(client.paramContract()).resolves.toEqual(contract);
    await expect(client.listLooks()).resolves.toEqual(looks);
    const preview = await client.preview({ path: "a.jpg", analysis: {}, factor: 0.8 });

    expect(preview.type).toBe("image/jpeg");
    expect(new Uint8Array(await preview.arrayBuffer())).toEqual(jpeg);
  });

  it("读取安全拍摄信息", async () => {
    const queue = responseQueue([Response.json({ iso: 200, file_format: "JPEG" })]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    await expect(client.imageInfo("C:/照片/a.jpg")).resolves.toEqual({
      iso: 200,
      file_format: "JPEG",
    });
    expect(queue.requests[0].url).toBe("http://127.0.0.1:9/api/image-info");
  });

  it("浏览器上传使用 multipart 且不手写 Content-Type 边界", async () => {
    const queue = responseQueue([Response.json({ path: "C:/temp/photo.jpg" })]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);
    const file = new File([new Uint8Array([1, 2, 3])], "照片.jpg", { type: "image/jpeg" });

    await expect(client.upload(file)).resolves.toEqual({ path: "C:/temp/photo.jpg" });

    const request = queue.requests[0];
    expect(request.init.method).toBe("POST");
    expect(request.init.body).toBeInstanceOf(FormData);
    expect((request.init.body as FormData).get("file")).toBeInstanceOf(File);
    const headers = new Headers(request.init.headers);
    expect(headers.get("X-Looklift-Token")).toBe("token");
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("编码风格名路径并覆盖读取、报告和导出端点", async () => {
    const queue = responseQueue([
      Response.json({ summary: "测试" }),
      new Response("<html>报告</html>", { headers: { "Content-Type": "text/html" } }),
      Response.json({ preset: "C:/looks/a.xmp" }),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    expect(client.reportUrl("胶片 #1")).toBe(
      "http://127.0.0.1:9/report/%E8%83%B6%E7%89%87%20%231",
    );

    await client.getLook("胶片 #1");
    await client.report("胶片 #1");
    await client.exportLook("胶片 #1", { factor: 0.6 });

    expect(queue.requests.map((item) => item.url)).toEqual([
      "http://127.0.0.1:9/api/looks/%E8%83%B6%E7%89%87%20%231",
      "http://127.0.0.1:9/report/%E8%83%B6%E7%89%87%20%231",
      "http://127.0.0.1:9/api/looks/%E8%83%B6%E7%89%87%20%231/export",
    ]);
    expect(new Headers(queue.requests[1].init.headers).has("X-Looklift-Token")).toBe(false);
  });

  it("读取调用前供应商配置且不暴露密钥字段", async () => {
    const queue = responseQueue([Response.json({
      configured: true, provider: "ollama", model: "vision", base_url: "http://localhost",
      timeout: 300, has_key: false,
    })]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);
    await expect(client.config()).resolves.toMatchObject({ provider: "ollama", has_key: false });
    expect(queue.requests[0].url).toBe("http://127.0.0.1:9/api/config");
    expect(new Headers(queue.requests[0].init.headers).get("X-Looklift-Token")).toBe("token");
  });

  it("覆盖对话候选与正式会话端点，并透传取消信号", async () => {
    const snapshot = { id: "session-1", current_version_id: "version-1" };
    const queue = responseQueue([
      Response.json({ analysis: {}, changes: [] }),
      Response.json(snapshot),
      Response.json(snapshot),
      Response.json(snapshot),
      Response.json(snapshot),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);
    const controller = new AbortController();
    const analysis = {} as Analysis;

    await client.chatStep(
      {
        path: "C:/照片/a.jpg",
        current_analysis: analysis,
        factor: 0.8,
        message: "提亮",
        history: [],
        include_metadata: true,
      },
      controller.signal,
    );
    await client.createSession({ path: "C:/照片/a.jpg", initial_analysis: analysis });
    await client.getSession("session-1");
    await client.commitSession("session-1", {
      exchange: [{ role: "user", content: "提亮" }],
      analysis,
      source: "chat",
    });
    await client.recordSessionMessages("session-1", {
      exchange: [{ role: "assistant", content: "失败", status: "failed" }],
    });

    expect(queue.requests.map((item) => item.url)).toEqual([
      "http://127.0.0.1:9/api/chat/step",
      "http://127.0.0.1:9/api/sessions",
      "http://127.0.0.1:9/api/sessions/session-1",
      "http://127.0.0.1:9/api/sessions/session-1/commit",
      "http://127.0.0.1:9/api/sessions/session-1/messages",
    ]);
    expect(queue.requests[0].init.signal).toBe(controller.signal);
    expect(JSON.parse(String(queue.requests[3].init.body)).source).toBe("chat");
    for (const request of queue.requests) {
      expect(new Headers(request.init.headers).get("X-Looklift-Token")).toBe("token");
    }
  });

  it("读取有上限的最近正式会话摘要", async () => {
    const sessions = [{
      id: "session-1",
      display_name: "照片.jpg",
      updated_at: "2026-07-20T04:00:00+00:00",
      current_version_id: "version-1",
      summary: "柔和暖调",
      source_available: true,
    }];
    const queue = responseQueue([Response.json({ sessions })]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    await expect(client.recentSessions(3)).resolves.toEqual(sessions);

    expect(queue.requests[0].url).toBe("http://127.0.0.1:9/api/sessions?limit=3");
  });

  it("覆盖图库分页、异步扫描、标签和 Explorer 端点", async () => {
    const queue = responseQueue([
      Response.json({ roots: [] }),
      Response.json({ task_id: "scan-1" }, { status: 202 }),
      Response.json({ status: "running", scanned: 2 }),
      Response.json({ ok: true }),
      Response.json({ items: [], total: 0, page: 2, page_size: 24 }),
      Response.json({ ok: true }),
      Response.json({ ok: true }),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    await client.libraryRoots();
    await client.scanLibraryRoot("root/1");
    await client.libraryScan("scan/1");
    await client.cancelLibraryScan("scan/1");
    await client.libraryItems("海边", "旅行", 2, 24);
    await client.setLibraryTags("item/1", ["旅行"]);
    await client.revealLibraryItem("item/1");

    expect(queue.requests.map((request) => request.url)).toEqual([
      "http://127.0.0.1:9/api/library/roots",
      "http://127.0.0.1:9/api/library/roots/root%2F1/scan",
      "http://127.0.0.1:9/api/library/scans/scan%2F1",
      "http://127.0.0.1:9/api/library/scans/scan%2F1/cancel",
      "http://127.0.0.1:9/api/library/items?keyword=%E6%B5%B7%E8%BE%B9&tag=%E6%97%85%E8%A1%8C&page=2&page_size=24",
      "http://127.0.0.1:9/api/library/items/item%2F1/tags",
      "http://127.0.0.1:9/api/library/items/item%2F1/reveal",
    ]);
  });

  it("优先透传后端中文错误，并为非 JSON 和网络错误提供稳定文案", async () => {
    const queue = responseQueue([
      Response.json({ error: "缺少 analysis 字段" }, { status: 400 }),
      Response.json({ error: "风格库中已存在同名条目：胶片" }, { status: 409 }),
      new Response("bad gateway", { status: 502 }),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    await expect(client.paramContract()).rejects.toMatchObject({
      message: "缺少 analysis 字段",
      status: 400,
    });
    await expect(client.saveLook({ name: "胶片", analysis: {} as Analysis })).rejects.toMatchObject({
      message: "风格库中已存在同名条目：胶片",
      status: 409,
    });
    await expect(client.ping()).rejects.toThrow("本地引擎请求失败（HTTP 502）");

    const offline = new LookliftClient("http://127.0.0.1:9", "token", async () => {
      throw new TypeError("fetch failed");
    });
    await expect(offline.ping()).rejects.toThrow("无法连接本地引擎：TypeError: fetch failed");
  });
});
