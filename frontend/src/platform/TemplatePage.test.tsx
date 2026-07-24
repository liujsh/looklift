// @vitest-environment happy-dom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { TemplateCard } from "../api/types";
import { TemplatePage } from "./TemplatePage";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const official: TemplateCard = {
  name: "青橙经典", summary: "冷暖分离", source: "built_in", readonly: true,
  suitable_for: ["旅行"], principles: ["冷暖互补建立层次"], steps: ["压低高光"],
  key_parameters: [{ path: "basic.highlights", value: -20 }],
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

  it("展示官方教学并把模板套用到 Studio", async () => {
    const onApply = vi.fn();
    const client = { listTemplates: vi.fn().mockResolvedValue([official]) };
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply onApply={onApply} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("青橙经典");
    expect(container.textContent).toContain("冷暖互补建立层次");
    expect(container.textContent).toContain("高光");
    expect(container.textContent).toContain("-20");

    await act(async () => {
      (container.querySelector("button.template-apply") as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(onApply).toHaveBeenCalledWith("青橙经典");
  });

  it("没有 Studio 时禁用套用并给出引导", async () => {
    const client = { listTemplates: vi.fn().mockResolvedValue([official]) };
    await act(async () => {
      root.render(<TemplatePage client={client as unknown as LookliftClient} canApply={false} onApply={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("请先从图库或快速修图打开一张照片");
    expect((container.querySelector("button.template-apply") as HTMLButtonElement).disabled).toBe(true);
  });
});
