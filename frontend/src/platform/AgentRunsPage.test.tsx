// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { AgentRunManifest } from "../api/types";
import { AgentRunsPage } from "./AgentRunsPage";

const interrupted: AgentRunManifest = {
  run_id: "run-a", status: "interrupted", baseline_hash: "a".repeat(64), photo_hash: "b".repeat(64),
  attempt_id: "attempt-1", last_sequence: 4, last_candidate_revision: "candidate-1", stale_reason: null,
  runtime_id: "pydantic-api", provider: "anthropic", model: "claude-test", domain_pack_hash: "c".repeat(64), session_id: "session-a",
};

describe("AgentRunsPage", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  it("展示运行事实并只通过新 Attempt 恢复", async () => {
    const resumeAgentRun = vi.fn().mockResolvedValue({ ...interrupted, status: "starting" });
    const client = {
      recoverableAgentRuns: vi.fn().mockResolvedValueOnce([interrupted]).mockResolvedValueOnce([]),
      runtimes: vi.fn().mockResolvedValue([
        { id: "pydantic-api", kind: "api", capabilities: [], supports_resume: false, supports_mcp: false, models: [] },
        { id: "pi-cli", kind: "cli", capabilities: [], supports_resume: true, supports_mcp: true, models: [] },
      ]),
      resumeAgentRun,
    } as unknown as LookliftClient;

    await act(async () => root.render(<AgentRunsPage client={client} />));
    await vi.waitFor(() => expect(container.textContent).toContain("candidate-1"));
    const select = container.querySelector("select")!;
    select.value = "pi-cli";
    await act(async () => select.dispatchEvent(new Event("change", { bubbles: true })));
    const button = [...container.querySelectorAll("button")].find((item) => item.textContent === "新建 Attempt")!;
    await act(async () => button.click());
    await vi.waitFor(() => expect(resumeAgentRun).toHaveBeenCalled());
    expect(resumeAgentRun.mock.calls[0][0]).toBe("run-a");
    expect(resumeAgentRun.mock.calls[0][2]).toBe("pi-cli");
  });

  it("stale 运行不展示恢复按钮", async () => {
    const client = {
      recoverableAgentRuns: vi.fn().mockResolvedValue([{ ...interrupted, status: "stale" }]),
      runtimes: vi.fn().mockResolvedValue([]),
    } as unknown as LookliftClient;
    await act(async () => root.render(<AgentRunsPage client={client} />));
    await vi.waitFor(() => expect(container.textContent).toContain("正式基线已变化"));
    expect([...container.querySelectorAll("button")].some((item) => item.textContent === "新建 Attempt")).toBe(false);
  });
});
