// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { ContextEntryView, ProposalView } from "../api/types";
import { SettingsPage } from "./SettingsPage";

const entries: ContextEntryView[] = [
  { id: "rule-natural", type: "rule", name: "自然优先", description: "", content: "禁止过度处理", source: "user", scope: "global", confirmed: true, enabled: true, version: 2, content_hash: "a".repeat(64), created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-25T00:00:00Z" },
  { id: "preference-warm", type: "preference", name: "暖色偏好", description: "", content: "肤色略暖", source: "connector", scope: "global", confirmed: true, enabled: true, version: 1, content_hash: "b".repeat(64), created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-25T00:00:00Z" },
  { id: "project-catalog", type: "project", name: "商品目录", description: "", content: "曝光保持一致", source: "user", scope: "project", confirmed: true, enabled: true, version: 3, content_hash: "c".repeat(64), created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-25T00:00:00Z" },
];

const proposal: ProposalView = {
  proposal_id: "proposal-a", target_type: "Memory", target_id: "preference-warm",
  base_hash: "b".repeat(64), patch: { content: "肤色保持中性" }, source_packet_ids: ["packet-a"],
  expires_at: "2026-08-26T00:00:00Z", status: "preview", applied_revision: null,
};

describe("SettingsPage", () => {
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

  function client(overrides = {}) {
    return {
      providerConfig: vi.fn().mockResolvedValue({ contract_version: 1, configured: false, has_key: false }),
      saveProviderConfig: vi.fn().mockResolvedValue({ ok: true, config_version: 1, has_key: true }),
      deleteProviderConfig: vi.fn().mockResolvedValue({ ok: true }),
      detectProvider: vi.fn().mockResolvedValue({ available: true, models: ["gpt-5"] }),
      runtimes: vi.fn().mockResolvedValue([
        { id: "pi-cli", kind: "cli", display_name: "Pi", support_level: "stable", capabilities: ["proxy_image"], supports_resume: true, supports_mcp: true, models: [] },
        { id: "openai-api", kind: "api", display_name: "OpenAI API", support_level: "experimental", capabilities: ["proxy_image"], supports_resume: false, supports_mcp: false, models: [] },
      ]),
      detectRuntimes: vi.fn().mockResolvedValue([]),
      saveConfig: vi.fn().mockResolvedValue({ ok: true }),
      contextTree: vi.fn().mockResolvedValue({ schema_version: 1, config: { enabled: true, auto_extract: false }, entries }),
      proposals: vi.fn().mockResolvedValue([proposal]),
      updateContextConfig: vi.fn().mockResolvedValue({ enabled: true, auto_extract: true }),
      saveContextEntry: vi.fn().mockResolvedValue(entries[0]),
      disableContextEntry: vi.fn().mockResolvedValue({ ...entries[0], enabled: false }),
      confirmProposal: vi.fn().mockResolvedValue({ ...proposal, status: "confirmed" }),
      rejectProposal: vi.fn().mockResolvedValue({ ...proposal, status: "rejected" }),
      applyProposal: vi.fn().mockResolvedValue({ ...proposal, status: "applied" }),
      ...overrides,
    } as unknown as LookliftClient;
  }

  it("分区展示规则、记忆、项目上下文和来源摘要", async () => {
    await act(async () => root.render(<SettingsPage client={client()} />));
    await vi.waitFor(() => expect(container.textContent).toContain("自然优先"));

    expect(container.textContent).toContain("全局规则");
    expect(container.textContent).toContain("记忆");
    expect(container.textContent).toContain("项目上下文");
    expect(container.textContent).toContain("connector · v1");
    expect(container.textContent).toContain("bbbbbbbbbbbb");
    expect((container.querySelector('input[name="auto_extract"]') as HTMLInputElement).checked).toBe(false);
  });

  it("审核 Proposal 后重新加载服务端事实", async () => {
    const confirmProposal = vi.fn().mockResolvedValue({ ...proposal, status: "confirmed" });
    const contextTree = vi.fn().mockResolvedValue({ schema_version: 1, config: { enabled: true, auto_extract: false }, entries });
    const proposals = vi.fn().mockResolvedValue([proposal]);
    const current = client({ confirmProposal, contextTree, proposals });
    await act(async () => root.render(<SettingsPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("肤色保持中性"));
    expect(container.textContent).toContain("肤色略暖");

    const confirm = [...container.querySelectorAll("button")].find((button) => button.textContent === "确认提案")!;
    await act(async () => confirm.click());

    await vi.waitFor(() => expect(confirmProposal).toHaveBeenCalledWith("proposal-a"));
    expect(contextTree).toHaveBeenCalledTimes(2);
    expect(proposals).toHaveBeenCalledTimes(2);
  });

  it("用户可直接保存已确认条目", async () => {
    const saveContextEntry = vi.fn().mockResolvedValue(entries[0]);
    const current = client({ saveContextEntry });
    await act(async () => root.render(<SettingsPage client={current} />));
    await vi.waitFor(() => expect(container.textContent).toContain("新增或编辑上下文"));

    const id = container.querySelector('input[name="entry_id"]') as HTMLInputElement;
    const content = container.querySelector('textarea[name="content"]') as HTMLTextAreaElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(id, "fact-camera");
      id.dispatchEvent(new Event("input", { bubbles: true }));
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(content, "使用同一机身");
      content.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const save = [...container.querySelectorAll("button")].find((button) => button.textContent === "保存上下文")!;
    await act(async () => save.click());

    await vi.waitFor(() => expect(saveContextEntry).toHaveBeenCalledWith("fact-camera", expect.objectContaining({ content: "使用同一机身" })));
  });

  it("区分本机 CLI 与 API，并在 Ollama 下隐藏密钥", async () => {
    await act(async () => root.render(<SettingsPage client={client()} />));
    await vi.waitFor(() => expect(container.textContent).toContain("Pi"));
    expect(container.textContent).toContain("正式");

    const apiMode = [...container.querySelectorAll("button")].find((button) => button.textContent === "API 提供商")!;
    await act(async () => apiMode.click());
    expect(container.querySelector('input[type="password"]')).not.toBeNull();

    const ollama = [...container.querySelectorAll("button")].find((button) => button.textContent === "Ollama")!;
    await act(async () => ollama.click());
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.textContent).toContain("请求仅发送到本机");
  });
});
