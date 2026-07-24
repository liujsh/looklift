// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AutomationPlan, AutomationRun, AutomationWorkflow } from "../api/types";
import { AutomationPage } from "./AutomationPage";

const workflow: AutomationWorkflow = {
  id: "workflow-1",
  name: "日常胶片",
  look_name: "柔和胶片",
  factor: .8,
  suffix: "-film",
  quality: 92,
  created_at: "2026-07-24",
};

const plan: AutomationPlan = {
  id: "plan-1",
  workflow,
  output_dir: "C:/输出",
  ready: true,
  created_at: "2026-07-24",
  items: [{ source: "C:/照片/a.jpg", output: "C:/输出/a-film.jpg", status: "ready", error: null }],
};

const finished: AutomationRun = {
  id: "run-1",
  plan_id: plan.id,
  workflow,
  status: "done",
  created_at: "2026-07-24",
  updated_at: "2026-07-24",
  items: [{ ...plan.items[0], status: "completed" }],
  total: 1,
  completed: 1,
  failed: 0,
  cancelled: 0,
};

describe("AutomationPage", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
    vi.stubGlobal("URL", {
      ...URL,
      createObjectURL: vi.fn(() => "blob:preview"),
      revokeObjectURL: vi.fn(),
    });
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
  });

  it("生成首张预览计划并确认执行", async () => {
    const client = {
      listLooks: vi.fn().mockResolvedValue([{ name: "柔和胶片", summary: "", source: "built_in", readonly: true, has_preset: false }]),
      listAutomationWorkflows: vi.fn().mockResolvedValue([workflow]),
      listAutomationRuns: vi.fn().mockResolvedValue([]),
      planAutomation: vi.fn().mockResolvedValue(plan),
      getLook: vi.fn().mockResolvedValue({ basic: {} }),
      preview: vi.fn().mockResolvedValue(new Blob(["jpeg"])),
      startAutomationRun: vi.fn().mockResolvedValue({ run_id: "run-1" }),
      automationRun: vi.fn().mockResolvedValue(finished),
    };
    await act(async () => {
      root.render(<AutomationPage
        client={client as never}
        chooseInputs={async () => ["C:/照片/a.jpg"]}
        chooseOutput={async () => "C:/输出"}
      />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const buttons = () => [...container.querySelectorAll("button")];
    await act(async () => {
      buttons().find((button) => button.textContent === "选择照片")?.click();
      await Promise.resolve();
      buttons().find((button) => button.textContent === "选择输出目录")?.click();
      await Promise.resolve();
    });
    await act(async () => {
      buttons().find((button) => button.textContent === "生成预览计划")?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("计划可以执行");
    expect(container.querySelector('img[alt="首张应用技能后的效果预览"]')).not.toBeNull();
    expect(client.planAutomation).toHaveBeenCalledWith({
      workflow_id: workflow.id,
      inputs: ["C:/照片/a.jpg"],
      output_dir: "C:/输出",
    });

    await act(async () => {
      buttons().find((button) => button.textContent === "确认并开始批量成片")?.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.textContent).toContain("1/1 完成");
    expect(client.startAutomationRun).toHaveBeenCalledWith(plan.id);
  });

  it("冲突计划不能执行", async () => {
    const conflict = {
      ...plan,
      ready: false,
      items: [{ ...plan.items[0], status: "conflict", error: "输出文件已存在" }],
    } satisfies AutomationPlan;
    const client = {
      listLooks: vi.fn().mockResolvedValue([{ name: "柔和胶片" }]),
      listAutomationWorkflows: vi.fn().mockResolvedValue([workflow]),
      listAutomationRuns: vi.fn().mockResolvedValue([]),
      planAutomation: vi.fn().mockResolvedValue(conflict),
      getLook: vi.fn(),
      preview: vi.fn(),
    };
    await act(async () => {
      root.render(<AutomationPage client={client as never} chooseInputs={async () => ["a.jpg"]} chooseOutput={async () => "C:/输出"} />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const buttons = () => [...container.querySelectorAll("button")];
    await act(async () => {
      buttons().find((button) => button.textContent === "选择照片")?.click();
      await Promise.resolve();
      buttons().find((button) => button.textContent === "选择输出目录")?.click();
      await Promise.resolve();
    });
    await act(async () => {
      buttons().find((button) => button.textContent === "生成预览计划")?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("请先解决计划中的冲突");
    expect(container.textContent).toContain("输出文件已存在");
    expect((buttons().find((button) => button.textContent === "确认并开始批量成片") as HTMLButtonElement).disabled).toBe(true);
    expect(client.preview).not.toHaveBeenCalled();
  });
});
