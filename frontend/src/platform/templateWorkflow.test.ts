import { describe, expect, it, vi } from "vitest";
import { applyTemplateToStudio } from "./templateWorkflow";

describe("applyTemplateToStudio", () => {
  it("通过正式 Store 和会话链路套用模板", async () => {
    const analysis = { basic: { contrast: 12 } } as never;
    const persisted = { basic: { contrast: 12 }, summary: "服务端确认" } as never;
    const runtime = {
      store: {
        getSnapshot: vi.fn().mockReturnValue({ activeAiRequestId: null, pendingPreview: null }),
        beginAiRequest: vi.fn().mockReturnValue(true),
        endAiRequest: vi.fn().mockReturnValue(true),
        setFactor: vi.fn(),
        commitAnalysis: vi.fn().mockReturnValue(true),
      },
      coordinator: { commitFormal: vi.fn().mockResolvedValue({ current_analysis: persisted }) },
    };
    const client = { getLook: vi.fn().mockResolvedValue(analysis) };

    await applyTemplateToStudio(client as never, runtime as never, "青橙经典");

    expect(client.getLook).toHaveBeenCalledWith("青橙经典");
    expect(runtime.store.setFactor).toHaveBeenCalledWith(1);
    expect(runtime.store.beginAiRequest).toHaveBeenCalledOnce();
    expect(runtime.store.endAiRequest).toHaveBeenCalledOnce();
    expect(runtime.coordinator.commitFormal).toHaveBeenCalledWith(analysis, "library");
    expect(runtime.store.commitAnalysis).toHaveBeenCalledWith(persisted, "library");
    expect(runtime.coordinator.commitFormal.mock.invocationCallOrder[0]).toBeLessThan(
      runtime.store.commitAnalysis.mock.invocationCallOrder[0],
    );
  });

  it.each([
    [{ activeAiRequestId: 7, pendingPreview: null }, "AI 修改"],
    [{ activeAiRequestId: null, pendingPreview: {} }, "待确认版本"],
  ])("Studio 存在%s时不读取模板或写入会话", async (snapshot, label) => {
    const runtime = {
      store: {
        getSnapshot: vi.fn().mockReturnValue(snapshot),
        beginAiRequest: vi.fn(),
        endAiRequest: vi.fn(),
        setFactor: vi.fn(),
        commitAnalysis: vi.fn(),
      },
      coordinator: { commitFormal: vi.fn() },
    };
    const client = { getLook: vi.fn().mockResolvedValue({}) };
    await expect(applyTemplateToStudio(
      client as never,
      runtime as never,
      "柔和胶片",
    )).rejects.toThrow(`Studio 正在处理${label}`);
    expect(client.getLook).not.toHaveBeenCalled();
    expect(runtime.coordinator.commitFormal).not.toHaveBeenCalled();
    expect(runtime.store.commitAnalysis).not.toHaveBeenCalled();
  });

  it("会话保存失败时不改变本地参数、强度或历史", async () => {
    const runtime = {
      store: {
        getSnapshot: vi.fn().mockReturnValue({ activeAiRequestId: null, pendingPreview: null }),
        beginAiRequest: vi.fn().mockReturnValue(true),
        endAiRequest: vi.fn().mockReturnValue(true),
        setFactor: vi.fn(),
        commitAnalysis: vi.fn(),
      },
      coordinator: { commitFormal: vi.fn().mockRejectedValue(new Error("磁盘已满")) },
    };

    await expect(applyTemplateToStudio(
      { getLook: vi.fn().mockResolvedValue({ basic: { contrast: 12 } }) } as never,
      runtime as never,
      "柔和胶片",
    )).rejects.toThrow("磁盘已满");

    expect(runtime.store.setFactor).not.toHaveBeenCalled();
    expect(runtime.store.commitAnalysis).not.toHaveBeenCalled();
    expect(runtime.store.endAiRequest).toHaveBeenCalledOnce();
  });
});
