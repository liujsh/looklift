import { describe, expect, it } from "vitest";
import { LookliftClient, clientFromStatus, readSidecarStatus } from "./client";
import type { SidecarStatus } from "./types";

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

  it("编码风格名路径并覆盖读取、报告和导出端点", async () => {
    const queue = responseQueue([
      Response.json({ summary: "测试" }),
      new Response("<html>报告</html>", { headers: { "Content-Type": "text/html" } }),
      Response.json({ preset: "C:/looks/a.xmp" }),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

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

  it("优先透传后端中文错误，并为非 JSON 和网络错误提供稳定文案", async () => {
    const queue = responseQueue([
      Response.json({ error: "缺少 analysis 字段" }, { status: 400 }),
      new Response("bad gateway", { status: 502 }),
    ]);
    const client = new LookliftClient("http://127.0.0.1:9", "token", queue.fetchFn);

    await expect(client.paramContract()).rejects.toMatchObject({
      message: "缺少 analysis 字段",
      status: 400,
    });
    await expect(client.ping()).rejects.toThrow("本地引擎请求失败（HTTP 502）");

    const offline = new LookliftClient("http://127.0.0.1:9", "token", async () => {
      throw new TypeError("fetch failed");
    });
    await expect(offline.ping()).rejects.toThrow("无法连接本地引擎：TypeError: fetch failed");
  });
});
