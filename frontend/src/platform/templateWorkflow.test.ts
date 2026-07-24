import { describe, expect, it, vi } from "vitest";
import { applyTemplateToStudio } from "./templateWorkflow";

describe("applyTemplateToStudio", () => {
  it("通过正式 Store 和会话链路套用模板", async () => {
    const analysis = { basic: { contrast: 12 } } as never;
    const runtime = {
      store: { setFactor: vi.fn(), commitAnalysis: vi.fn().mockReturnValue(true) },
      coordinator: { commitFormal: vi.fn().mockResolvedValue(undefined) },
    };
    const client = { getLook: vi.fn().mockResolvedValue(analysis) };

    await applyTemplateToStudio(client as never, runtime as never, "青橙经典");

    expect(client.getLook).toHaveBeenCalledWith("青橙经典");
    expect(runtime.store.setFactor).toHaveBeenCalledWith(1);
    expect(runtime.store.commitAnalysis).toHaveBeenCalledWith(analysis, "library");
    expect(runtime.coordinator.commitFormal).toHaveBeenCalledWith(analysis, "library");
  });

  it("Studio 被锁定时不写入会话版本", async () => {
    const runtime = {
      store: { setFactor: vi.fn(), commitAnalysis: vi.fn().mockReturnValue(false) },
      coordinator: { commitFormal: vi.fn() },
    };
    await expect(applyTemplateToStudio(
      { getLook: vi.fn().mockResolvedValue({}) } as never,
      runtime as never,
      "柔和胶片",
    )).rejects.toThrow("Studio 正在处理其他修改");
    expect(runtime.coordinator.commitFormal).not.toHaveBeenCalled();
  });
});
