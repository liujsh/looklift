// @vitest-environment happy-dom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { Analysis, TemplateCard } from "../api/types";
import { TemplatePage } from "./TemplatePage";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const official: TemplateCard = {
  name: "青橙经典", summary: "冷暖分离", source: "built_in", readonly: true, category: "movie",
  suitable_for: ["旅行", "城市夜景"], principles: ["冷暖互补建立层次"], steps: ["压低高光"],
  key_parameters: [{ path: "basic.highlights", value: -20 }],
};

const portrait: TemplateCard = {
  ...official, name: "柔和胶片", summary: "柔和自然光", category: "portrait", suitable_for: ["自然光人像"],
};

const user: TemplateCard = {
  ...official, name: "我的风格", source: "user", readonly: false, category: "uncategorized",
};

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
}

const fullAnalysis: Analysis = {
  summary: "完整模板参数", steps: ["压低高光"],
  basic: { temperature_shift: 5, tint_shift: 0, exposure: 0, contrast: 12, highlights: -20, shadows: 8, whites: 0, blacks: -4, texture: 0, clarity: 3, dehaze: 0, vibrance: 6, saturation: -2 },
  tone_curve: [{ input: 0, output: 5 }, { input: 100, output: 96 }],
  hsl: [{ color: "orange", hue: -4, saturation: 12, luminance: 8 }],
  color_grading: {
    shadows: { hue: 190, saturation: 14, luminance: 0 }, midtones: { hue: 0, saturation: 0, luminance: 0 },
    highlights: { hue: 40, saturation: 9, luminance: 0 }, global_: { hue: 0, saturation: 0, luminance: 0 }, blending: 50, balance: 0,
  },
  effects: { vignette_amount: -8, grain_amount: 10 },
};

describe("TemplatePage", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.restoreAllMocks();
  });

  it("目录页保持简洁，点击卡片后才进入详情并显示应用按钮", async () => {
    const onApply = vi.fn();
    const client = { listTemplates: vi.fn().mockResolvedValue([official, portrait]), getLook: vi.fn().mockResolvedValue(fullAnalysis) };
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply onApply={onApply} />);
      await settle();
    });

    expect(container.querySelectorAll(".template-contact-card")).toHaveLength(2);
    expect(container.querySelector(".template-contact-card")?.textContent).not.toContain("应用到当前照片");
    expect(container.querySelector("button.template-detail-apply")).toBeNull();

    await act(async () => {
      (container.querySelector(".template-contact-card") as HTMLButtonElement).click();
      await settle();
    });
    expect(container.querySelector(".template-detail-page")).not.toBeNull();
    expect(container.querySelector('button[aria-label="返回模板目录"]')?.textContent).toBe("");
    expect(container.querySelector('button[aria-label="应用到当前照片"]')?.textContent).toBe("");
    expect(container.textContent).toContain("HSL 颜色");
    expect(container.textContent).toContain("明亮度");
    expect(container.querySelector(".template-parameter-panel")?.textContent).not.toContain("曝光+0");

    await act(async () => {
      const saturationTab = Array.from(container.querySelectorAll(".template-hsl-tabs button")).find((button) => button.textContent === "饱和度") as HTMLButtonElement;
      saturationTab.click();
    });
    expect(container.querySelector(".template-hsl-row")?.textContent).toContain("+12");

    await act(async () => {
      const showAll = Array.from(container.querySelectorAll(".template-mode-switch button")).find((button) => button.textContent === "显示全部") as HTMLButtonElement;
      showAll.click();
    });
    expect(container.querySelector(".template-parameter-panel")?.textContent).toContain("曝光");

    await act(async () => {
      (container.querySelector("button.template-detail-apply") as HTMLButtonElement).click();
      await settle();
    });
    expect(onApply).toHaveBeenCalledWith("青橙经典");
  });

  it("来源、分类和搜索可以组合筛选且目录不常驻详情", async () => {
    const client = { listTemplates: vi.fn().mockResolvedValue([official, portrait, user]) };
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply onApply={vi.fn()} />);
      await settle();
    });

    await act(async () => (container.querySelector('button[data-category="portrait"]') as HTMLButtonElement).click());
    expect(container.querySelector(".template-catalog-grid")?.textContent).toContain("柔和胶片");
    expect(container.querySelector(".template-catalog-grid")?.textContent).not.toContain("青橙经典");
    expect(container.querySelector(".template-detail-page")).toBeNull();

    await act(async () => {
      const search = container.querySelector('input[aria-label="搜索模板"]') as HTMLInputElement;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(search, "没有结果");
      search.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("没有匹配的模板");

    await act(async () => (container.querySelector('button[data-source="user"]') as HTMLButtonElement).click());
    expect(container.textContent).toContain("未分类");
  });

  it("没有合法照片预览时明确回退到白盒参数指纹", async () => {
    const client = { listTemplates: vi.fn().mockResolvedValue([official]), getLook: vi.fn().mockResolvedValue(fullAnalysis) };
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply={false} onApply={vi.fn()} />);
      await settle();
    });

    await act(async () => {
      (container.querySelector(".template-contact-card") as HTMLButtonElement).click();
      await settle();
    });
    expect(container.querySelector(".tone-fingerprint")).not.toBeNull();
    expect(container.textContent).toContain("不是照片效果图");
    expect(container.textContent).toContain("请先从图库或快速修图打开一张照片");
    expect((container.querySelector("button.template-detail-apply") as HTMLButtonElement).disabled).toBe(true);
  });

  it("打开照片后用选中模板参数生成真实临时对比且不提交", async () => {
    vi.spyOn(URL, "createObjectURL").mockReturnValueOnce("blob:before").mockReturnValueOnce("blob:after");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    const client = {
      listTemplates: vi.fn().mockResolvedValue([official]),
      getLook: vi.fn().mockResolvedValue(fullAnalysis),
      preview: vi.fn().mockResolvedValue(new Blob(["image"])),
    };
    const onApply = vi.fn();
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply currentPhoto={{ path: "C:/photo.jpg", title: "photo.jpg" }} onApply={onApply} />);
      await settle();
    });
    await act(async () => {
      (container.querySelector(".template-contact-card") as HTMLButtonElement).click();
      await settle();
      await settle();
    });

    expect(client.getLook).toHaveBeenCalledWith("青橙经典");
    expect(client.preview).toHaveBeenCalledTimes(2);
    expect(client.preview.mock.calls.map((call) => call[0].factor).sort()).toEqual([0, 1]);
    expect(container.querySelector('img[alt="原片"]')).not.toBeNull();
    expect(container.querySelector('img[alt="模板效果"]')).not.toBeNull();
    expect(onApply).not.toHaveBeenCalled();
  });

  it("读取失败时展示稳定错误", async () => {
    const client = { listTemplates: vi.fn().mockRejectedValue(new Error("引擎不可用")) };
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply onApply={vi.fn()} />);
      await settle();
    });
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("模板载入失败");
    expect(container.textContent).toContain("引擎不可用");
  });
});
