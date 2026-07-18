import { describe, expect, it } from "vitest";
import { canvasErrorMessage, firstSupportedImage, loadPreviewPair, previewSignature } from "./canvasModel";

describe("canvasModel", () => {
  it("从真实拖放路径中选择第一个受支持图片", () => {
    expect(firstSupportedImage(["C:/notes.txt", "C:/PHOTO.TIFF", "C:/other.jpg"]))
      .toBe("C:/PHOTO.TIFF");
    expect(firstSupportedImage(["C:/notes.txt", "C:/archive.zip"])).toBeNull();
  });

  it("before 与 after 使用同一路径和 analysis，只改变 factor", async () => {
    const calls: Array<{ path: string; analysis: Record<string, unknown>; factor: number }> = [];
    const before = new Blob(["before"], { type: "image/jpeg" });
    const after = new Blob(["after"], { type: "image/jpeg" });
    const analysis = { basic: { exposure: 1 } };
    const client = {
      async preview(payload: { path: string; analysis: Record<string, unknown>; factor: number }) {
        calls.push(payload);
        return payload.factor === 0 ? before : after;
      },
      async upload() { return { path: "unused" }; },
    };

    await expect(loadPreviewPair(client, "C:/photo.jpg", analysis, 0.75))
      .resolves.toEqual({ before, after });
    expect(calls).toEqual([
      { path: "C:/photo.jpg", analysis, factor: 0 },
      { path: "C:/photo.jpg", analysis, factor: 0.75 },
    ]);
  });

  it("保留可操作中文错误并为未知异常补充上下文", () => {
    expect(canvasErrorMessage(new Error("文件不存在"))).toBe("文件不存在");
    expect(canvasErrorMessage("连接中断")).toBe("无法载入照片：连接中断");
  });

  it("预览签名同时区分路径、参数和强度", () => {
    const base = previewSignature("C:/photo.jpg", { basic: { exposure: 1 } }, 1);
    expect(previewSignature("C:/other.jpg", { basic: { exposure: 1 } }, 1)).not.toBe(base);
    expect(previewSignature("C:/photo.jpg", { basic: { exposure: 2 } }, 1)).not.toBe(base);
    expect(previewSignature("C:/photo.jpg", { basic: { exposure: 1 } }, 0.7)).not.toBe(base);
  });
});
