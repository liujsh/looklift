import { useEffect, useMemo, useState, type FormEvent } from "react";
import type { LookliftClient } from "../api/client";
import type { ContextEntryType, ContextEntryView, ContextTreeView, ProposalView } from "../api/types";

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

export function SettingsPage({ client }: { client: LookliftClient }) {
  const [provider, setProvider] = useState({ provider: "auto", model: "", base_url: "", timeout: "", api_key: "" });
  const [context, setContext] = useState(EMPTY_CONTEXT);
  const [proposals, setProposals] = useState<ProposalView[]>([]);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [status, setStatus] = useState("正在读取设置…");

  const loadContext = async () => {
    const [tree, nextProposals] = await Promise.all([client.contextTree(), client.proposals()]);
    setContext(tree);
    setProposals(nextProposals);
  };

  useEffect(() => {
    void Promise.all([
      client.config().then((cfg) => setProvider({ provider: cfg.provider, model: cfg.model, base_url: cfg.base_url, timeout: String(cfg.timeout ?? ""), api_key: "" })),
      loadContext(),
    ]).then(() => setStatus(""), () => setStatus("设置读取失败"));
  }, [client]);

  const grouped = useMemo(() => ({
    rules: context.entries.filter((entry) => entry.type === "rule"),
    memory: context.entries.filter((entry) => entry.type !== "rule" && entry.type !== "project"),
    projects: context.entries.filter((entry) => entry.type === "project"),
  }), [context.entries]);

  const saveProvider = async (event: FormEvent) => {
    event.preventDefault();
    setStatus("正在保存模型配置…");
    try {
      await client.saveConfig({ ...provider, timeout: provider.timeout ? Number(provider.timeout) : "" });
      setStatus("模型配置已保存");
    } catch (reason) {
      setStatus(reason instanceof Error ? reason.message : "保存失败");
    }
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

    <section className="settings-section" aria-labelledby="provider-settings">
      <h2 id="provider-settings">模型 Runtime</h2>
      <p>API 与 CLI 使用同一领域契约；密钥只提交给本地引擎。</p>
      <form className="settings-provider-form" onSubmit={saveProvider}>
        <label>供应商<select value={provider.provider} onChange={(event) => setProvider({ ...provider, provider: event.target.value })}><option value="auto">自动选择</option><option value="cli">Claude Code CLI</option><option value="api">Anthropic API</option><option value="openai_compat">OpenAI 兼容</option><option value="ollama">Ollama</option></select></label>
        <label>模型<input value={provider.model} onChange={(event) => setProvider({ ...provider, model: event.target.value })} /></label>
        <label>Base URL<input value={provider.base_url} onChange={(event) => setProvider({ ...provider, base_url: event.target.value })} /></label>
        <label>API Key<input type="password" value={provider.api_key} onChange={(event) => setProvider({ ...provider, api_key: event.target.value })} placeholder="留空则保留" /></label>
        <label>超时（秒）<input value={provider.timeout} onChange={(event) => setProvider({ ...provider, timeout: event.target.value })} /></label>
        <button type="submit">保存模型配置</button>
      </form>
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
