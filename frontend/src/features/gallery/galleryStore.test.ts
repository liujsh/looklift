import { describe, expect, it, vi } from "vitest";
import type { Analysis, LookSummary } from "../../api/types";
import { loadLookIntoEditor, looksForSource } from "./galleryStore";

const looks: LookSummary[] = [
  { name: "青橙经典", summary: "冷暖对比", has_preset: false, source: "built_in", readonly: true },
  { name: "我的风格", summary: "用户收藏", has_preset: true, source: "user", readonly: false },
];

describe("galleryStore", () => {
  it("按内置与用户来源稳定分组", () => {
    expect(looksForSource(looks, "built_in").map((look) => look.name)).toEqual(["青橙经典"]);
    expect(looksForSource(looks, "user").map((look) => look.name)).toEqual(["我的风格"]);
  });

  it("载入卡片后把完整 analysis 交给单一 editorStore 入口", async () => {
    const analysis = { summary: "载入结果" } as Analysis;
    const client = { getLook: vi.fn(async () => analysis) };
    const commit = vi.fn();

    await expect(loadLookIntoEditor(client, "青橙经典", commit)).resolves.toBe(analysis);
    expect(client.getLook).toHaveBeenCalledWith("青橙经典");
    expect(commit).toHaveBeenCalledWith(analysis, 1);
  });
});
