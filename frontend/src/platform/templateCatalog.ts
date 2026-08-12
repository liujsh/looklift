import type { TemplateCard, TemplateCategory } from "../api/types";

export type TemplateCategoryFilter = "all" | TemplateCategory;

const PARAMETER_LABELS: Record<string, string> = {
  temperature_shift: "色温", tint_shift: "色调", exposure: "曝光", contrast: "对比度", highlights: "高光",
  shadows: "阴影", whites: "白色色阶", blacks: "黑色色阶", texture: "纹理", clarity: "清晰度",
  dehaze: "去朦胧", vibrance: "自然饱和度", saturation: "饱和度", hue: "色相",
  vignette_amount: "暗角", grain_amount: "颗粒",
};

export function templateParameterLabel(path: string): string {
  const parts = path.split(".");
  const leaf = parts[parts.length - 1] ?? path;
  const section = parts.length > 2 ? `${parts[parts.length - 2]} · ` : "";
  return `${section}${PARAMETER_LABELS[leaf] ?? leaf}`;
}

export const TEMPLATE_CATEGORIES: ReadonlyArray<{ id: TemplateCategoryFilter; label: string }> = [
  { id: "all", label: "全部" },
  { id: "portrait", label: "人像" },
  { id: "nature", label: "自然" },
  { id: "movie", label: "电影" },
  { id: "black_white", label: "黑白" },
  { id: "night", label: "夜景" },
  { id: "travel", label: "旅行" },
];

export function templateCategoryLabel(category: TemplateCategory): string {
  return TEMPLATE_CATEGORIES.find((item) => item.id === category)?.label ?? "未分类";
}

export function visibleTemplateCategories(
  templates: readonly TemplateCard[],
  source: TemplateCard["source"],
): ReadonlyArray<{ id: TemplateCategoryFilter; label: string }> {
  const hasUncategorized = templates.some((item) => item.source === source && item.category === "uncategorized");
  return hasUncategorized
    ? [...TEMPLATE_CATEGORIES, { id: "uncategorized" as const, label: "未分类" }]
    : TEMPLATE_CATEGORIES;
}

export function filterTemplates(
  templates: readonly TemplateCard[],
  filter: { source: TemplateCard["source"]; category: TemplateCategoryFilter; query: string },
): TemplateCard[] {
  const query = filter.query.trim().toLocaleLowerCase("zh-CN");
  return templates.filter((template) => {
    if (template.source !== filter.source) return false;
    if (filter.category !== "all" && template.category !== filter.category) return false;
    if (!query) return true;
    return [
      template.name,
      template.summary,
      templateCategoryLabel(template.category),
      ...template.suitable_for,
    ].some((value) => value.toLocaleLowerCase("zh-CN").includes(query));
  });
}

export function countTemplates(
  templates: readonly TemplateCard[],
  source: TemplateCard["source"],
  category: TemplateCategoryFilter,
): number {
  return templates.filter((item) => item.source === source && (category === "all" || item.category === category)).length;
}
