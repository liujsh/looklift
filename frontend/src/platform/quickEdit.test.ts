import { describe, expect, it, vi } from "vitest";
import type { Analysis, SessionSnapshot } from "../api/types";
import { runQuickEdit, type QuickEditDependencies } from "./quickEdit";

const analysis = { summary: "", steps: [] } as unknown as Analysis;
const snapshot = {
  id: "session-1",
  image_path: "C:/照片/a.jpg",
  current_analysis: analysis,
} as SessionSnapshot;

function dependencies(overrides: Partial<QuickEditDependencies> = {}): QuickEditDependencies {
  return {
    initialAnalysis: analysis,
    chooseBrowserFile: vi.fn().mockResolvedValue(null),
    upload: vi.fn().mockResolvedValue({ path: "C:/temp/upload.jpg" }),
    createSession: vi.fn().mockResolvedValue(snapshot),
    openSession: vi.fn(),
    ...overrides,
  };
}

describe("runQuickEdit", () => {
  it("原生选择成功后使用真实路径创建或恢复会话", async () => {
    const deps = dependencies({ chooseNativePath: vi.fn().mockResolvedValue("C:/照片/a.jpg") });

    await expect(runQuickEdit(deps)).resolves.toBe("opened");

    expect(deps.upload).not.toHaveBeenCalled();
    expect(deps.createSession).toHaveBeenCalledWith({ path: "C:/照片/a.jpg", initial_analysis: analysis });
    expect(deps.openSession).toHaveBeenCalledWith(snapshot);
  });

  it("取消原生选择不上传、不创建标签", async () => {
    const deps = dependencies({ chooseNativePath: vi.fn().mockResolvedValue(null) });

    await expect(runQuickEdit(deps)).resolves.toBe("cancelled");

    expect(deps.chooseBrowserFile).not.toHaveBeenCalled();
    expect(deps.createSession).not.toHaveBeenCalled();
    expect(deps.openSession).not.toHaveBeenCalled();
  });

  it("原生能力不可用时使用浏览器上传回退", async () => {
    const file = new File(["image"], "upload.jpg", { type: "image/jpeg" });
    const deps = dependencies({ chooseBrowserFile: vi.fn().mockResolvedValue(file) });

    await expect(runQuickEdit(deps)).resolves.toBe("opened");

    expect(deps.upload).toHaveBeenCalledWith(file);
    expect(deps.createSession).toHaveBeenCalledWith({ path: "C:/temp/upload.jpg", initial_analysis: analysis });
    expect(deps.openSession).toHaveBeenCalledWith(snapshot);
  });

  it.each([
    ["上传失败", { chooseBrowserFile: vi.fn().mockResolvedValue(new File(["x"], "a.jpg")), upload: vi.fn().mockRejectedValue(new Error("上传失败")) }],
    ["会话失败", { chooseNativePath: vi.fn().mockResolvedValue("C:/照片/a.jpg"), createSession: vi.fn().mockRejectedValue(new Error("会话失败")) }],
  ])("%s 时不打开空标签", async (_label, overrides) => {
    const deps = dependencies(overrides);

    await expect(runQuickEdit(deps)).rejects.toThrow();
    expect(deps.openSession).not.toHaveBeenCalled();
  });
});
