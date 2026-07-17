import { describe, expect, it, vi } from "vitest";
import type { Analysis, LookSummary } from "../../api/types";
import { exportLookFile, openLookReport, saveCurrentLook } from "./lookActions";

const analysis = { summary: "当前调色" } as Analysis;
const userLook: LookSummary = {
  name: "我的风格", summary: "当前调色", has_preset: true, source: "user", readonly: false,
};

describe("lookActions", () => {
  it("收藏完整 analysis 与 factor，成功后重拉图库", async () => {
    const client = {
      saveLook: vi.fn(async () => ({ name: "我的风格" })),
      listLooks: vi.fn(async () => [userLook]),
    };

    await expect(saveCurrentLook(client, " 我的风格 ", analysis, 0.7)).resolves.toEqual({
      name: "我的风格",
      looks: [userLook],
    });
    expect(client.saveLook).toHaveBeenCalledWith({ name: "我的风格", analysis, factor: 0.7 });
    expect(client.listLooks).toHaveBeenCalledOnce();
  });

  it("报告使用经过编码的本地 URL 并在新窗口打开", () => {
    const open = vi.fn();
    const client = { reportUrl: vi.fn(() => "http://127.0.0.1:9/report/%E8%83%B6%E7%89%87") };

    openLookReport(client, "胶片", open);

    expect(client.reportUrl).toHaveBeenCalledWith("胶片");
    expect(open).toHaveBeenCalledWith(
      "http://127.0.0.1:9/report/%E8%83%B6%E7%89%87", "_blank", "noopener,noreferrer",
    );
  });

  it("预设与 sidecar 导出返回后端实际文件路径", async () => {
    const client = {
      exportLook: vi.fn()
        .mockResolvedValueOnce({ preset: "C:/looks/a.xmp" })
        .mockResolvedValueOnce({ sidecar: "C:/raw/a.xmp" }),
    };

    await expect(exportLookFile(client, "胶片")).resolves.toBe("C:/looks/a.xmp");
    await expect(exportLookFile(client, "胶片", "C:/raw/a.cr3")).resolves.toBe("C:/raw/a.xmp");
    expect(client.exportLook).toHaveBeenNthCalledWith(1, "胶片", {});
    expect(client.exportLook).toHaveBeenNthCalledWith(2, "胶片", { sidecar: "C:/raw/a.cr3" });
  });
});
