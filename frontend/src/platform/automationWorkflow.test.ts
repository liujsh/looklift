import { describe, expect, it, vi } from "vitest";
import type { AutomationRun } from "../api/types";
import { waitForAutomationRun } from "./automationWorkflow";

const base = {
  id: "run-1",
  plan_id: "plan-1",
  workflow: {
    id: "workflow-1", name: "胶片", look_name: "柔和胶片", factor: .8,
    suffix: "-film", quality: 92, created_at: "2026-07-24",
  },
  created_at: "2026-07-24",
  updated_at: "2026-07-24",
  items: [],
  total: 1,
  completed: 0,
  failed: 0,
  cancelled: 0,
} satisfies Omit<AutomationRun, "status">;

describe("waitForAutomationRun", () => {
  it("持续轮询直到任务进入终态", async () => {
    const running = { ...base, status: "running" } satisfies AutomationRun;
    const done = { ...base, status: "done", completed: 1 } satisfies AutomationRun;
    const automationRun = vi.fn().mockResolvedValueOnce(running).mockResolvedValueOnce(done);
    const progress = vi.fn();

    await expect(waitForAutomationRun({ automationRun } as never, "run-1", progress, undefined, 0)).resolves.toEqual(done);
    expect(progress).toHaveBeenCalledTimes(2);
  });

  it("外部取消后不再发请求", async () => {
    const controller = new AbortController();
    controller.abort();
    const automationRun = vi.fn();

    await expect(waitForAutomationRun({ automationRun } as never, "run-1", vi.fn(), controller.signal, 0))
      .rejects.toMatchObject({ name: "AbortError" });
    expect(automationRun).not.toHaveBeenCalled();
  });
});
