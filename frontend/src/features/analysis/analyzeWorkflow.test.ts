import { afterEach, describe, expect, it, vi } from "vitest";
import type { Analysis, TaskResult } from "../../api/types";
import { analyzeImage } from "./analyzeWorkflow";

const analysis = {
  summary: "AI 分析结果",
  steps: [],
  basic: {
    temperature_shift: 0,
    tint_shift: 0,
    exposure: 0,
    contrast: 0,
    highlights: 0,
    shadows: 0,
    whites: 0,
    blacks: 0,
    texture: 0,
    clarity: 0,
    dehaze: 0,
    vibrance: 0,
    saturation: 0,
  },
  tone_curve: [{ input: 0, output: 0 }, { input: 1, output: 1 }],
  hsl: [],
  color_grading: {
    shadows: { hue: 0, saturation: 0, luminance: 0 },
    midtones: { hue: 0, saturation: 0, luminance: 0 },
    highlights: { hue: 0, saturation: 0, luminance: 0 },
    global_: { hue: 0, saturation: 0, luminance: 0 },
    blending: 50,
    balance: 0,
  },
  effects: { vignette_amount: 0, grain_amount: 0 },
} satisfies Analysis;

afterEach(() => vi.useRealTimers());

describe("analyzeImage", () => {
  it("提交图片并轮询到完整 analysis", async () => {
    vi.useFakeTimers();
    const client = {
      analyze: vi.fn(async () => ({ task_id: "task-1" })),
      task: vi.fn()
        .mockResolvedValueOnce({ status: "running", message: "分析中", result: null, error: null })
        .mockResolvedValueOnce({ status: "done", message: null, result: analysis, error: null }),
    };

    const pending = analyzeImage(client, "C:/照片/a.jpg", { pollInterval: 20 });
    await vi.advanceTimersByTimeAsync(20);

    await expect(pending).resolves.toBe(analysis);
    expect(client.analyze).toHaveBeenCalledWith({ path: "C:/照片/a.jpg" });
    expect(client.task).toHaveBeenCalledTimes(2);
  });

  it("透传后台任务的中文失败原因", async () => {
    const client = {
      analyze: vi.fn(async () => ({ task_id: "task-2" })),
      task: vi.fn(async (): Promise<TaskResult> => ({
        status: "error", message: null, result: null, error: "未配置可用的 AI 后端",
      })),
    };

    await expect(analyzeImage(client, "a.jpg", { pollInterval: 0 }))
      .rejects.toThrow("未配置可用的 AI 后端");
  });

  it("拒绝没有完整结果的 done 任务", async () => {
    const client = {
      analyze: vi.fn(async () => ({ task_id: "task-3" })),
      task: vi.fn(async (): Promise<TaskResult> => (
        { status: "done", message: null, result: null, error: null }
      )),
    };

    await expect(analyzeImage(client, "a.jpg", { pollInterval: 0 }))
      .rejects.toThrow("AI 分析完成，但没有返回参数结果");
  });

  it("新图片载入时可取消旧分析轮询", async () => {
    const controller = new AbortController();
    controller.abort();
    const client = {
      analyze: vi.fn(async () => ({ task_id: "unused" })),
      task: vi.fn(async (): Promise<TaskResult> => (
        { status: "running", message: null, result: null, error: null }
      )),
    };

    await expect(analyzeImage(client, "a.jpg", { signal: controller.signal }))
      .rejects.toMatchObject({ name: "AbortError" });
    expect(client.analyze).not.toHaveBeenCalled();
  });
});
