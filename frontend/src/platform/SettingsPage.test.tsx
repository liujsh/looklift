// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { ContextEntryView, ProposalView } from "../api/types";
import { SettingsPage } from "./SettingsPage";

const entries: ContextEntryView[] = [
  { id: "rule-natural", type: "rule", name: "自然优先", description: "", content: "禁止过度处理", source: "user", scope: "global", state: "active", project_id: null, run_id: null, expires_at: null, confidence: 1, evidence: "", enabled: true, version: 2, content_hash: "a".repeat(64), created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-25T00:00:00Z" },
  { id: "preference-warm", type: "preference", name: "暖色偏好", description: "", content: "肤色略暖", source: "connector", scope: "global", state: "active", project_id: null, run_id: null, expires_at: null, confidence: 0.94, evidence: "两次修图反馈", enabled: true, version: 1, content_hash: "b".repeat(64), created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-25T00:00:00Z" },
  { id: "project-catalog", type: "project", name: "商品目录", description: "", content: "曝光保持一致", source: "user", scope: "project", state: "disabled", project_id: "catalog", run_id: null, expires_at: null, confidence: 1, evidence: "", enabled: false, version: 3, content_hash: "c".repeat(64), created_at: "2026-08-24T00:00:00Z", updated_at: "2026-08-25T00:00:00Z" },
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
      exportDiagnostics: vi.fn().mockResolvedValue({ ok: true, path: "C:/诊断/diagnostics.json", event_count: 2 }),
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

  async function openSection(label: string) {
    const button = [...container.querySelectorAll(".settings-nav nav button")].find((item) => item.textContent === label) as HTMLButtonElement;
    await act(async () => button.click());
  }

  it("分区展示规则、记忆、项目上下文和来源摘要", async () => {
    await act(async () => root.render(<SettingsPage client={client()} />));
    await vi.waitFor(() => expect(container.textContent).toContain("模型与提供商"));
    await openSection("指令与记忆");
    await vi.waitFor(() => expect(container.textContent).toContain("自然优先"));

    expect(container.textContent).toContain("全局规则");
    expect(container.textContent).toContain("记忆");
    expect(container.textContent).toContain("项目上下文");
    expect(container.textContent).toContain("connector · v1");
    expect(container.textContent).toContain("bbbbbbbbbbbb");
    expect(container.textContent?.match(/已启用/g)).toHaveLength(2);
    expect(container.textContent).toContain("已停用");
    expect(container.textContent).not.toMatch(/已确认|待确认/);
    await openSection("通用与隐私");
    expect((container.querySelector('input[name="auto_extract"]') as HTMLInputElement).checked).toBe(false);
  });

  it("不再展示 Proposal 审核面板", async () => {
    await act(async () => root.render(<SettingsPage client={client()} />));
    expect(container.textContent).not.toContain("待审核提案");
    expect(container.textContent).not.toContain("确认提案");
  });

  it("用户可直接保存启用条目", async () => {
    const saveContextEntry = vi.fn().mockResolvedValue(entries[0]);
    const current = client({ saveContextEntry });
    await act(async () => root.render(<SettingsPage client={current} />));
    await openSection("指令与记忆");
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

    const ollama = [...container.querySelectorAll("button")].find((button) => button.textContent === "本机 Ollama")!;
    await act(async () => ollama.click());
    expect(container.querySelector('input[type="password"]')).toBeNull();
    expect(container.textContent).toContain("请求仅发送到本机");
  });

  it("切换 Provider 时隔离保留未提交表单", async () => {
    await act(async () => root.render(<SettingsPage client={client()} />));
    await vi.waitFor(() => expect(container.textContent).toContain("Pi"));
    const click = async (text: string) => {
      const button = [...container.querySelectorAll("button")].find((item) => item.textContent === text)!;
      await act(async () => button.click());
    };
    const fill = async (input: HTMLInputElement, value: string) => {
      await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    };

    await click("API 提供商");
    await fill(container.querySelector('input[placeholder="例如 gpt-5"]') as HTMLInputElement, "gpt-5-mini");
    await click("本机 Ollama");
    await fill(container.querySelector('input[placeholder="例如 qwen3"]') as HTMLInputElement, "qwen3:8b");
    await click("OpenAI / 兼容接口");
    expect((container.querySelector('input[placeholder="例如 gpt-5"]') as HTMLInputElement).value).toBe("gpt-5-mini");
    await click("本机 Ollama");
    expect((container.querySelector('input[placeholder="例如 qwen3"]') as HTMLInputElement).value).toBe("qwen3:8b");
  });

  it("隐私分区提供脱敏诊断导出", async () => {
    const exportDiagnostics = vi.fn().mockResolvedValue({ ok: true, path: "C:/诊断/diagnostics.json", event_count: 2 });
    await act(async () => root.render(<SettingsPage client={client({ exportDiagnostics })} />));
    await openSection("通用与隐私");
    const button = [...container.querySelectorAll("button")].find((item) => item.textContent === "导出诊断信息");
    expect(button).toBeTruthy();
    await act(async () => (button as HTMLButtonElement).click());
    await vi.waitFor(() => expect(exportDiagnostics).toHaveBeenCalledTimes(1));
    expect(container.textContent).toContain("诊断信息已导出");
  });

  it("重新扫描失败时显示可操作状态", async () => {
    const detectRuntimes = vi.fn().mockRejectedValue(new Error("CLI 扫描失败，请检查安装路径"));
    await act(async () => root.render(<SettingsPage client={client({ detectRuntimes })} />));
    await vi.waitFor(() => expect(container.textContent).toContain("Pi"));

    const rescan = [...container.querySelectorAll("button")].find((button) => button.textContent?.includes("重新扫描"))!;
    await act(async () => rescan.click());

    await vi.waitFor(() => expect(container.textContent).toContain("CLI 扫描失败，请检查安装路径"));
  });
});
