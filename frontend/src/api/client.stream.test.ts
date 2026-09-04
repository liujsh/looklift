import { describe, expect, it, vi } from "vitest";
import { LookliftClient, parseSseBlock } from "./client";
import type { HarnessEvent } from "./types";

describe("parseSseBlock", () => {
  it("解析统一的 harness 事件帧", () => {
    const event = parseSseBlock(
      'event: harness\ndata: {"type":"run_started","run_id":"r","attempt_id":"a","sequence":1,"payload":{}}',
    );
    expect(event).toEqual({
      type: "run_started",
      run_id: "r",
      attempt_id: "a",
      sequence: 1,
      payload: {},
    });
  });

  it("忽略非 harness 帧与空数据", () => {
    expect(parseSseBlock("event: other\ndata: x")).toBeNull();
    expect(parseSseBlock("event: harness")).toBeNull();
    expect(parseSseBlock("")).toBeNull();
  });

  it("拒绝缺少 type/sequence 的非法载荷", () => {
    expect(parseSseBlock('event: harness\ndata: {"type":"run_started"}')).toBeNull();
    expect(parseSseBlock("event: harness\ndata: not-json")).toBeNull();
  });
});

function streamResponse(frames: string[]): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame));
      controller.close();
    },
  });
  return new Response(stream, { status: 200 });
}

describe("LookliftClient.streamAgentRun", () => {
  it("把 SSE 帧映射为统一 Harness 事件并停止于终态", async () => {
    const fetchFn = vi.fn(async () =>
      streamResponse([
        'event: harness\ndata: {"type":"run_started","run_id":"r","attempt_id":"a","sequence":1,"payload":{}}\n\n',
        'event: harness\ndata: {"type":"run_finished","run_id":"r","attempt_id":"a","sequence":2,"payload":{"outcome":"completed"}}\n\n',
      ]),
    );
    const client = new LookliftClient("http://127.0.0.1:43123", "tok", fetchFn as typeof fetch);

    const events: HarnessEvent[] = [];
    await client.streamAgentRun(
      {
        runId: "r",
        attemptId: "a",
        runtimeId: "openai-api",
        executionMode: "api",
        model: "gpt-test",
        instructions: "只生成白盒候选",
        userMessage: "自然提亮",
        proxyJpegBase64: "aGVsbG8=",
      },
      (event) => events.push(event),
    );

    expect(events.map((event) => event.type)).toEqual(["run_started", "run_finished"]);
    const call = fetchFn.mock.calls[0] as unknown as [string, RequestInit];
    const body = JSON.parse(String(call[1].body));
    expect(body.runtime_id).toBe("openai-api");
    expect(body.execution_mode).toBe("api");
    expect(body.cli_available).toBe(false);
    expect(body.domain_pack.instructions).toBe("只生成白盒候选");
    expect(body.proxy_jpeg).toBe("aGVsbG8=");
    const headers = new Headers(call[1].headers);
    expect(headers.get("X-Looklift-Token")).toBe("tok");
  });

  it("跨 chunk 边界的 SSE 块能正确重组", async () => {
    const half = 'event: harness\ndata: {"type":"text_delta","run_id":"r","attempt_id":"a","sequence":1,"payload":';
    const rest = '{"text":"hi"}}\n\n';
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(half));
        controller.enqueue(encoder.encode(rest));
        controller.close();
      },
    });
    const client = new LookliftClient(
      "http://127.0.0.1:43123",
      "tok",
      (async () => new Response(stream, { status: 200 })) as typeof fetch,
    );
    const events: HarnessEvent[] = [];
    await client.streamAgentRun(
      {
        runId: "r",
        attemptId: "a",
        runtimeId: "openai-api",
        executionMode: "api",
        model: "m",
        instructions: "i",
        userMessage: "u",
        proxyJpegBase64: "x",
      },
      (event) => events.push(event),
    );
    expect(events).toHaveLength(1);
    expect(events[0].type).toBe("text_delta");
  });
});
