import { describe, expect, it } from "vitest";
import type { TemplateCard } from "../api/types";
import { filterTemplates, visibleTemplateCategories } from "./templateCatalog";

const cards: TemplateCard[] = [
  {
    name: "柔和胶片", summary: "低反差生活感", source: "built_in", readonly: true,
    category: "portrait", suitable_for: ["自然光人像"], principles: [], steps: [], key_parameters: [],
  },
  {
    name: "城市青橙", summary: "冷暖分离", source: "built_in", readonly: true,
    category: "movie", suitable_for: ["城市夜景"], principles: [], steps: [], key_parameters: [],
  },
  {
    name: "我的雨夜", summary: "低饱和", source: "user", readonly: false,
    category: "uncategorized", suitable_for: ["夜雨街头"], principles: [], steps: [], key_parameters: [],
  },
];

describe("模板目录筛选", () => {
  it("来源和分类是两个正交维度", () => {
    expect(filterTemplates(cards, { source: "built_in", category: "portrait", query: "" }).map((x) => x.name)).toEqual(["柔和胶片"]);
    expect(filterTemplates(cards, { source: "user", category: "portrait", query: "" })).toEqual([]);
  });

  it("搜索名称、摘要、分类名称和适用场景", () => {
    expect(filterTemplates(cards, { source: "built_in", category: "all", query: "夜景" }).map((x) => x.name)).toEqual(["城市青橙"]);
    expect(filterTemplates(cards, { source: "built_in", category: "all", query: "人像" }).map((x) => x.name)).toEqual(["柔和胶片"]);
    expect(filterTemplates(cards, { source: "built_in", category: "all", query: "电影" }).map((x) => x.name)).toEqual(["城市青橙"]);
  });

  it("未分类只在当前来源确有未分类模板时出现", () => {
    expect(visibleTemplateCategories(cards, "built_in").map((x) => x.id)).not.toContain("uncategorized");
    expect(visibleTemplateCategories(cards, "user").map((x) => x.id)).toContain("uncategorized");
  });
});
