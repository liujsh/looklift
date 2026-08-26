import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { LookliftClient } from "../api/client";
import type { ContextEntryType, ContextEntryView, ContextTreeView, ProposalView, RuntimeSummary } from "../api/types";

const EMPTY_CONTEXT: ContextTreeView = {
  schema_version: 1,
  config: { enabled: true, auto_extract: false },
  entries: [],
};

const TYPE_LABELS: Record<ContextEntryType, string> = {
  profile: "个人资料", rule: "全局规则", fact: "事实", preference: "偏好",
  project: "项目上下文", reference: "参考", feedback: "反馈",
};

type EntryDraft = { id: string; type: ContextEntryType; name: string; content: string; scope: ContextEntryView["scope"] };
const EMPTY_DRAFT: EntryDraft = { id: "", type: "preference", name: "", content: "", scope: "global" };
type ProviderDraft = { model: string; base_url: string; max_tokens: string; api_key: string };
const EMPTY_PROVIDER_DRAFTS: Record<"openai" | "ollama", ProviderDraft> = {
  openai: { model: "", base_url: "https://api.openai.com/v1", max_tokens: "4096", api_key: "" },
  ollama: { model: "", base_url: "http://127.0.0.1:11434/v1", max_tokens: "4096", api_key: "" },
};

const CAPABILITY_LABELS: Record<string, string> = {
  proxy_image: "代理图",
  structured_events: "结构化事件",
  tool_calling: "工具调用",
  mcp: "MCP",
};

export function SettingsPage({ client }: { client: LookliftClient }) {
  const [providerId, setProviderId] = useState<"openai" | "ollama">("openai");
  const [providerDrafts, setProviderDrafts] = useState(EMPTY_PROVIDER_DRAFTS);
  const provider = providerDrafts[providerId];
  const updateProvider = (patch: Partial<ProviderDraft>) => setProviderDrafts((current) => ({ ...current, [providerId]: { ...current[providerId], ...patch } }));
  const [context, setContext] = useState(EMPTY_CONTEXT);
  const [proposals, setProposals] = useState<ProposalView[]>([]);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [status, setStatus] = useState("正在读取设置…");
  const [runtimeMode, setRuntimeMode] = useState<"cli" | "api">("cli");
  const [runtimes, setRuntimes] = useState<RuntimeSummary[]>([]);

  const loadContext = async () => {
    const [tree, nextProposals] = await Promise.all([client.contextTree(), client.proposals()]);
    setContext(tree);
    setProposals(nextProposals);
  };

  useEffect(() => {
    void Promise.all([
      client.providerConfig().then((cfg) => { if (cfg.configured) { const id = cfg.provider_id ?? "openai"; setProviderId(id); setProviderDrafts((current) => ({ ...current, [id]: { model: cfg.model ?? "", base_url: cfg.base_url ?? "", max_tokens: String(cfg.max_tokens ?? 4096), api_key: "" } })); } }),
      client.runtimes().then(setRuntimes),
      loadContext(),
    ]).then(() => setStatus(""), () => setStatus("设置读取失败"));
  }, [client]);

  const grouped = useMemo(() => ({
    rules: context.entries.filter((entry) => entry.type === "rule"),
    memory: context.entries.filter((entry) => entry.type !== "rule" && entry.type !== "project"),
    projects: context.entries.filter((entry) => entry.type === "project"),
  }), [context.entries]);
  const cliRuntimes = useMemo(() => runtimes
    .filter((runtime) => runtime.kind === "cli")
    .sort((left, right) => Number(right.available !== false) - Number(left.available !== false)
      || Number(right.support_level === "stable") - Number(left.support_level === "stable")), [runtimes]);

  const saveProvider = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("正在保存模型配置…");
    try {
      await client.saveProviderConfig({ provider_id: providerId, model: provider.model, base_url: provider.base_url, max_tokens: Number(provider.max_tokens), api_key: provider.api_key || undefined });
      setStatus("模型配置已保存");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "保存失败");
    }
  };

  const rescanRuntimes = async () => {
    setStatus("正在重新扫描 Runtime…");
    try { setRuntimes(await client.detectRuntimes()); setStatus("Runtime 扫描完成"); }
    catch (reason) { setStatus(reason instanceof Error ? reason.message : "Runtime 扫描失败"); }
  };

  const deleteProvider = async () => {
    setStatus("正在删除 Provider 配置…");
    try { await client.deleteProviderConfig(); setProviderId("openai"); setProviderDrafts(EMPTY_PROVIDER_DRAFTS); setStatus("Provider 配置和凭据已删除"); }
    catch (reason) { setStatus(reason instanceof Error ? reason.message : "删除失败"); }
  };

  const detectProvider = async () => {
    setStatus("正在检测 Provider 连通性…");
    try { const result = await client.detectProvider(); setStatus(`连接成功，可用模型 ${result.models.length} 个`); }
    catch (reason) { setStatus(reason instanceof Error ? reason.message : "连通性检测失败"); }
  };

  const saveEntry = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("正在保存上下文…");
    try {
      await client.saveContextEntry(draft.id, { type: draft.type, content: draft.content, name: draft.name, scope: draft.scope });
      setDraft(EMPTY_DRAFT);
      await loadContext();
      setStatus("上下文已保存并确认");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "保存失败");
    }
  };

  const disable = async (id: string) => {
    setStatus("正在停用…");
    try {
      await client.disableContextEntry(id);
      await loadContext();
      setStatus("条目已停用");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "停用失败");
    }
  };

  const review = async (proposal: ProposalView, action: "confirm" | "reject" | "apply") => {
    setStatus("正在更新提案…");
    try {
      if (action === "confirm") await client.confirmProposal(proposal.proposal_id);
      else if (action === "reject") await client.rejectProposal(proposal.proposal_id);
      else await client.applyProposal(proposal.proposal_id);
      await loadContext();
      setStatus("提案状态已更新");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "提案更新失败");
    }
  };

  const toggleAutoExtract = async (enabled: boolean) => {
    try {
      const next = await client.updateContextConfig({ auto_extract: enabled });
      setContext((current) => ({ ...current, config: next }));
      setStatus("隐私设置已更新");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "隐私设置更新失败");
    }
  };

  return <main className="settings-page" aria-label="设置与帮助">
    <header><p className="pane-kicker">SETTINGS</p><h1>设置与上下文</h1><p>模型、长期上下文和外部提案都保存在本地，并在每次运行前冻结版本。</p></header>
    {status && <p role="status" className="settings-status">{status}</p>}

    <section className="settings-section provider-settings" aria-labelledby="provider-settings">
      <div className="provider-settings-title"><div><h2 id="provider-settings">模型与提供商</h2><p>选择运行提示词的本机 CLI，或配置由本地引擎安全保管凭据的 API。</p></div></div>
      <div className="provider-mode" role="tablist"><button type="button" role="tab" aria-selected={runtimeMode === "cli"} onClick={() => setRuntimeMode("cli")}>本机 CLI</button><button type="button" role="tab" aria-selected={runtimeMode === "api"} onClick={() => setRuntimeMode("api")}>API 提供商</button></div>
      {runtimeMode === "cli" ? <div className="runtime-panel" role="tabpanel">
        <div className="runtime-titlebar"><div><h3>你的 CLI <span>({cliRuntimes.length})</span></h3><p>已检测的入口会共享同一套候选版本与安全校验。</p></div><button type="button" onClick={() => void rescanRuntimes()}>↻ 重新扫描</button></div>
        <div className="runtime-list">{cliRuntimes.map((runtime, index) => <RuntimeCard key={runtime.id} runtime={runtime} primary={index === 0} />)}{cliRuntimes.length === 0 && <p className="runtime-empty">没有检测到本机 CLI。安装后点击“重新扫描”。</p>}</div>
      </div> : <div className="provider-panel" role="tabpanel">
        <div className="provider-capsules" aria-label="Provider 选择"><button type="button" aria-pressed={providerId === "openai"} onClick={() => setProviderId("openai")}>OpenAI / 兼容接口</button><button type="button" aria-pressed={providerId === "ollama"} onClick={() => setProviderId("ollama")}>本机 Ollama</button></div>
        <form className="settings-provider-form" onSubmit={saveProvider}>
          <div className="provider-form-heading"><div><h3>{providerId === "ollama" ? "Ollama API" : "OpenAI API"}</h3><p>{providerId === "ollama" ? "仅连接本机回环地址，不经过外部代理。" : "适用于 OpenAI 和采用 OpenAI 协议的 HTTPS 提供商。"}</p></div><span>{providerId === "ollama" ? "本机" : "远程"}</span></div>
          <p className="provider-notice">填写必填项后即可保存；当前已生效配置在保存成功前保持不变。</p>
          {providerId !== "ollama" && <label>API Key <span aria-hidden="true">*</span><input type="password" value={provider.api_key} onChange={(event) => updateProvider({ api_key: event.target.value })} placeholder="留空则保留现有密钥" /><small>密钥仅交给本机安全存储，查询接口和日志均不会回显。</small></label>}
          <label>Base URL <span aria-hidden="true">*</span><input value={provider.base_url} onChange={(event) => updateProvider({ base_url: event.target.value })} /></label>
          <label>最大 Token <small>可选</small><input inputMode="numeric" value={provider.max_tokens} onChange={(event) => updateProvider({ max_tokens: event.target.value })} /></label>
          <label>模型 <span aria-hidden="true">*</span><input value={provider.model} onChange={(event) => updateProvider({ model: event.target.value })} placeholder={providerId === "ollama" ? "例如 qwen3" : "例如 gpt-5"} /></label>
          <p className="provider-privacy">{providerId === "ollama" ? "请求仅发送到本机 Ollama，不经过外部代理。" : "代理图最长边 2048px、无 EXIF；发送前显示实际数据接收方。"}</p>
          <div className="provider-form-actions"><button type="button" onClick={() => void detectProvider()}>测试连接</button><button className="provider-delete" type="button" onClick={() => void deleteProvider()}>删除配置</button><button className="provider-save" type="submit">保存模型配置</button></div>
        </form>
      </div>}
    </section>

    <section className="settings-section" aria-labelledby="privacy-settings">
      <div className="settings-heading"><div><h2 id="privacy-settings">自动提取与隐私</h2><p>默认关闭。开启后也只生成待审核 Proposal，不会静默写入正式记忆。</p></div><label className="settings-switch"><input name="auto_extract" type="checkbox" checked={context.config.auto_extract} onChange={(event) => void toggleAutoExtract(event.target.checked)} />允许生成记忆提案</label></div>
    </section>

    <section className="settings-section" aria-labelledby="context-editor">
      <h2 id="context-editor">新增或编辑上下文</h2>
      <form className="context-entry-form" onSubmit={saveEntry}>
        <label>ID<input name="entry_id" required pattern="[a-z0-9-]+" value={draft.id} onChange={(event) => setDraft({ ...draft, id: event.target.value })} placeholder="preference-natural" /></label>
        <label>类型<select value={draft.type} onChange={(event) => setDraft({ ...draft, type: event.target.value as ContextEntryType })}>{Object.entries(TYPE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>名称<input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>作用域<select value={draft.scope} onChange={(event) => setDraft({ ...draft, scope: event.target.value as EntryDraft["scope"] })}><option value="global">全局</option><option value="project">项目</option><option value="run">单次运行</option></select></label>
        <label className="context-entry-content">内容<textarea name="content" required value={draft.content} onChange={(event) => setDraft({ ...draft, content: event.target.value })} /></label>
        <button type="submit">保存上下文</button>
      </form>
    </section>

    <div className="context-groups">
      <ContextGroup title="全局规则" entries={grouped.rules} onEdit={setDraft} onDisable={disable} />
      <ContextGroup title="记忆" entries={grouped.memory} onEdit={setDraft} onDisable={disable} />
      <ContextGroup title="项目上下文" entries={grouped.projects} onEdit={setDraft} onDisable={disable} />
    </div>

    <section className="settings-section" aria-labelledby="proposal-review">
      <h2 id="proposal-review">待审核 Proposal</h2>
      {proposals.filter((item) => !["applied", "rejected"].includes(item.status)).length === 0 && <p>没有待审核提案。</p>}
      <div className="proposal-list">{proposals.filter((item) => !["applied", "rejected"].includes(item.status)).map((item) => <article key={item.proposal_id} className="proposal-card">
        <header><strong>{item.target_id}</strong><span>{item.status}</span></header>
        <div className="proposal-diff"><div><small>当前</small><p>{context.entries.find((entry) => entry.id === item.target_id)?.content ?? "（目标不可见）"}</p></div><div><small>提议</small><p>{String(item.patch.content ?? "（无正文变更）")}</p></div></div>
        <small>来源：{item.source_packet_ids.join("、") || "Agent"} · 基线 {item.base_hash.slice(0, 12)}</small>
        <div>{item.status === "preview" && <><button type="button" onClick={() => void review(item, "confirm")}>确认提案</button><button type="button" onClick={() => void review(item, "reject")}>拒绝</button></>}{item.status === "confirmed" && <button type="button" onClick={() => void review(item, "apply")}>应用到正式上下文</button>}</div>
      </article>)}</div>
    </section>
  </main>;
}

function RuntimeCard({ runtime, primary }: { runtime: RuntimeSummary; primary: boolean }) {
  const state = runtime.available === false ? "未检测到" : runtime.authenticated === false ? "需要认证" : "可用";
  return <article className="runtime-card" data-primary={primary} data-available={runtime.available !== false}>
    <div className="runtime-mark" aria-hidden="true">{runtime.display_name.slice(0, 2)}</div>
    <div className="runtime-card-main"><header><div><strong>{runtime.display_name}</strong><small>{runtime.version ?? runtime.id}</small></div><div className="runtime-badges"><span data-state={runtime.available === false ? "missing" : "ready"}>{state}</span><span data-level={runtime.support_level}>{runtime.support_level === "stable" ? "正式" : "实验性"}</span></div></header>
      {primary && <><div className="runtime-capabilities">{runtime.capabilities.map((capability) => <span key={capability}>{CAPABILITY_LABELS[capability] ?? capability}</span>)}</div><p>{runtime.available === false ? runtime.error ?? "未找到可执行文件" : `${runtime.supports_mcp ? "支持 MCP" : "不支持 MCP"} · ${runtime.supports_resume ? "支持原生续接" : "使用事实恢复"}${runtime.models.length ? ` · ${runtime.models.length} 个模型` : ""}`}</p></>}
    </div>
  </article>;
}

function ContextGroup({ title, entries, onEdit, onDisable }: {
  title: string;
  entries: ContextEntryView[];
  onEdit: (draft: EntryDraft) => void;
  onDisable: (id: string) => Promise<void>;
}) {
  return <section className="settings-section context-group"><h2>{title}</h2>{entries.length === 0 && <p>暂无条目。</p>}{entries.map((entry) => <article key={entry.id} data-enabled={entry.enabled}>
    <header><strong>{entry.name || entry.id}</strong><span>{TYPE_LABELS[entry.type]}</span></header>
    <p>{entry.content}</p><small>{entry.source} · v{entry.version} · {entry.confirmed ? "已确认" : "待确认"} · {entry.content_hash.slice(0, 12)}</small>
    <div><button type="button" onClick={() => onEdit({ id: entry.id, type: entry.type, name: entry.name, content: entry.content, scope: entry.scope })}>编辑</button>{entry.enabled && <button type="button" onClick={() => void onDisable(entry.id)}>停用</button>}</div>
  </article>)}</section>;
}
