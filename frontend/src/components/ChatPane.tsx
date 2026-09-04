import { useSyncExternalStore, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { Analysis, RuntimeSummary, TemplateCard } from "../api/types";
import type { ChatWorkflow } from "../features/chat/chatWorkflow";
import type { SessionCoordinator } from "../features/sessions/sessionCoordinator";
import type { RenderStatus } from "../store/editorStore";
import { ChatChangeCard } from "./ChatChangeCard";
import { ChatMessageList } from "./ChatMessageList";
import { Icon } from "../platform/icons";

type ChatPaneProps = {
  enabled: boolean;
  workflow?: ChatWorkflow | null;
  coordinator?: SessionCoordinator | null;
  providerLabel?: string;
  renderStatus?: RenderStatus;
  client?: LookliftClient;
  onHome?(): void;
  onOpenSettings?(): void;
};

export type TemplatePromptAttachment = { template: TemplateCard; analysis: Analysis };
export type SkillAttachment = { id: string; name: string; description: string };

export function buildTemplatePrompt(message: string, attachment?: TemplatePromptAttachment | null): string {
  if (!attachment) return message;
  return [
    `用户要求：${message}`,
    `参考模板：${attachment.template.name}（${attachment.template.summary}）`,
    `模板白盒参数：${JSON.stringify(attachment.analysis)}`,
    "请结合当前照片自适应这些参数，不要机械覆盖；只修改现有白盒参数契约允许的字段。",
  ].join("\n");
}

export function buildSkillPrompt(message: string, skill?: SkillAttachment | null): string {
  if (!skill) return message;
  return [`用户要求：${message}`, `已选择技能：${skill.name}（${skill.description}）`, "请按该技能执行，并保持白盒参数可解释；不要重绘原照片。"].join("\n");
}

export async function submitChatInput(
  value: string, workflow: ChatWorkflow, attachment?: TemplatePromptAttachment | null, skill?: SkillAttachment | null,
) {
  const message = value.trim();
  if (!message) return null;
  return workflow.send(buildSkillPrompt(buildTemplatePrompt(message, attachment), skill));
}

const EMPTY = Object.freeze({
  phase: "idle" as const, messages: Object.freeze([]), lastResponse: null,
  error: null, round: 0, stopReason: null,
});
const emptySubscribe = () => () => {};

export function ChatPane({
  enabled,
  workflow,
  coordinator,
  providerLabel,
  renderStatus = "ready",
  client,
  onHome,
  onOpenSettings,
}: ChatPaneProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [input, setInput] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerMode, setPickerMode] = useState<"skill" | "template" | null>(null);
  const [templates, setTemplates] = useState<readonly TemplateCard[]>([]);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [attachment, setAttachment] = useState<TemplatePromptAttachment | null>(null);
  const [skillAttachment, setSkillAttachment] = useState<SkillAttachment | null>(null);
  const [runtimePickerOpen, setRuntimePickerOpen] = useState(false);
  const [runtimeOptions, setRuntimeOptions] = useState<RuntimeSummary[]>([]);
  const [selectedRuntime, setSelectedRuntime] = useState<{ id: string; name: string; model: string; kind: "cli" | "api" } | null>(null);
  const [pickerKind, setPickerKind] = useState<"cli" | "api">("cli");
  const skills: SkillAttachment[] = [
    { id: "abstract-collage", name: "抽象风格拼接", description: "生成照片衍生的抽象拼接参考" },
    { id: "zine-layout", name: "Zine / 小志排版", description: "整理照片叙事与版式建议" },
    { id: "film-look", name: "胶片质感", description: "模拟胶片色彩、颗粒与对比" },
  ];
  const loadRuntimeOptions = async (kind: "cli" | "api" = pickerKind) => {
    if (!client) return;
    try {
      setRuntimeOptions(
        (await client.runtimes()).filter((item) => item.enabled !== false && item.available !== false && (item.kind === "api" ? "api" : "cli") === kind),
      );
    } catch { setRuntimeOptions([]); }
  };
  const canSend = Boolean(selectedRuntime?.id && selectedRuntime.model);
  const sendHint = canSend ? null : "请先选择可用入口和模型";
  const state = useSyncExternalStore(
    workflow?.subscribe ?? emptySubscribe,
    workflow?.getSnapshot ?? (() => EMPTY),
    workflow?.getSnapshot ?? (() => EMPTY),
  );
  const response = state.lastResponse;
  const candidateReady = renderStatus === "ready";
  const act = async (action: () => Promise<unknown>) => {
    setActionError(null);
    setActionBusy(true);
    try { await action(); } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally { setActionBusy(false); }
  };
  const toggleTemplatePicker = async () => {
    const next = !(pickerOpen && pickerMode === "template");
    setPickerOpen(next);
    setPickerMode("template");
    if (!next || !client || templates.length > 0 || templateLoading) return;
    setTemplateLoading(true);
    setActionError(null);
    try { setTemplates(await client.listTemplates()); } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally { setTemplateLoading(false); }
  };
  const selectTemplate = async (template: TemplateCard) => {
    if (!client) return;
    setTemplateLoading(true);
    setActionError(null);
    try {
      setAttachment({ template, analysis: await client.getLook(template.name) });
      setPickerOpen(false);
      setPickerMode(null);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally { setTemplateLoading(false); }
  };

  return (
    <aside
      className="chat-pane"
      data-pane="chat"
      data-state={enabled ? "enabled" : "reserved"}
      aria-label="AI 对话"
      hidden={!enabled}
      data-collapsed={collapsed}
    >
      <header className="chat-heading">
        <div><p className="pane-kicker">Chat</p><h2>对话调整</h2></div>
        <div className="chat-heading-actions">
          <button className="chat-home" type="button" aria-label="返回主页" title="返回首页" onClick={onHome}>
            <Icon name="home" />
          </button>
          <button
            type="button"
            aria-label={collapsed ? "展开 AI 对话" : "折叠 AI 对话"}
            title={collapsed ? "展开对话" : "折叠对话"}
            onClick={() => setCollapsed(!collapsed)}
          >
            <Icon name="collapse" />
          </button>
        </div>
      </header>
      {!collapsed && <>
        <div className="chat-scroll">
          <ChatMessageList messages={state.messages} />
          {response && <ChatChangeCard changes={response.changes} />}
          {response && (response.limitations.length > 0 || response.approximation || response.manual_steps.length > 0) &&
            <section className="chat-limitations">
              {response.limitations.length > 0 && <div><strong>当前不能自动完成</strong><ul>{response.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
              {response.approximation && <div><strong>可用近似方案</strong><p>{response.approximation}</p></div>}
              {response.manual_steps.length > 0 && <div><strong>右侧面板手动步骤</strong><ol>{response.manual_steps.map((item) => <li key={item}>{item}</li>)}</ol></div>}
            </section>}
          {(state.error || actionError) && <div className="chat-error" role="alert">
            <strong>{state.error ?? actionError}</strong><span>可重试或继续手调，正式版本未改变。</span>
          </div>}
          {state.stopReason && <p className="chat-stop">本轮已停止：{{
            done: "效果已达成", no_changes: "没有有效变化", cancelled: "已取消", round_limit: "已达到两轮上限",
          }[state.stopReason]}</p>}
        </div>

        {state.phase === "pending" && <div className="chat-decisions" aria-label="候选版本操作">
          {!candidateReady && <p className="chat-render-status" role="status">
            {renderStatus === "error" ? "候选预览渲染失败，可撤销或重试" : "正在渲染候选预览…"}
          </p>}
          <button type="button" disabled={actionBusy || !candidateReady} className="primary" onClick={() => void act(async () => {
            await (coordinator?.acceptPending() ?? Promise.reject(new Error("会话尚未就绪")));
            workflow?.settlePending();
          })}>保留此版本</button>
          <button type="button" disabled={actionBusy} onClick={() => void act(async () => {
            await (coordinator?.discardPending() ?? Promise.reject(new Error("会话尚未就绪")));
            workflow?.settlePending();
          })}>撤销</button>
          <button type="button" disabled={actionBusy || !candidateReady || state.round >= 2} onClick={() => void act(() => workflow?.refine() ?? Promise.reject(new Error("AI 尚未就绪")))}>AI 精修</button>
          <button type="button" disabled={actionBusy || !candidateReady} onClick={() => void act(async () => {
            await (coordinator?.continueManual() ?? Promise.reject(new Error("会话尚未就绪")));
            workflow?.settlePending();
          })}>继续手调</button>
        </div>}

        {state.phase === "requesting" && <div className="chat-progress" aria-live="polite">
          <span>{state.round === 0 ? "正在分析修图要求" : `AI 精修第 ${state.round}/2 轮`}</span>
          <button type="button" onClick={() => workflow?.cancel()}>取消等待</button>
        </div>}

        <form className="chat-composer" onSubmit={(event) => {
          event.preventDefault();
          if (!workflow || !input.trim()) return;
          if (!canSend) { setActionError(sendHint); return; }
          const value = input;
          setInput("");
          void act(async () => {
            const result = await submitChatInput(value, workflow, attachment, skillAttachment);
            if (result) { setAttachment(null); setSkillAttachment(null); }
            void result;
          });
        }}>
          {(attachment || skillAttachment) && <div className="chat-template-chip">
            {skillAttachment && <span><Icon name="skill" />技能 · {skillAttachment.name}</span>}
            {skillAttachment && <button type="button" aria-label="移除技能附件" onClick={() => setSkillAttachment(null)}><Icon name="close" /></button>}
            {attachment && <span><Icon name="template" />模板 · {attachment.template.name}</span>}
            {attachment && <button type="button" aria-label="移除模板附件" onClick={() => setAttachment(null)}><Icon name="close" /></button>}
          </div>}
          {pickerOpen && !pickerMode && <div className="chat-template-picker" role="dialog" aria-label="添加技能或模板"><strong>添加到本轮</strong><button type="button" onClick={() => setPickerMode("skill")}>选择技能</button><button type="button" onClick={() => void toggleTemplatePicker()}>选择模板</button></div>}
          {pickerOpen && pickerMode === "skill" && <div className="chat-template-picker" role="dialog" aria-label="选择技能"><strong>选择技能</strong>{skills.map((skill) => <button type="button" key={skill.id} onClick={() => { setSkillAttachment(skill); setPickerOpen(false); setPickerMode(null); }}><span>{skill.name}</span><small>{skill.description}</small></button>)}</div>}
          {pickerOpen && pickerMode === "template" && <div className="chat-template-picker" role="dialog" aria-label="选择模板附件"><strong>选择模板作为 AI 参考</strong>{templates.map((template) => <button type="button" key={template.name} onClick={() => void selectTemplate(template)}>
              <span>{template.name}</span><small>{template.summary}</small>
            </button>)}
            {templateLoading && <span>正在载入模板…</span>}
          </div>}
          <button type="button" aria-label="添加技能或模板" title="添加技能或模板" onClick={() => { setPickerOpen((current) => !current); setPickerMode(null); }}>
            <Icon name="add" />
          </button>
          <button type="button" className="chat-runtime-trigger" aria-label="选择模型" onClick={() => { setRuntimePickerOpen((current) => !current); void loadRuntimeOptions(pickerKind); }}><span aria-hidden="true">{selectedRuntime?.kind === "api" ? "◇" : "◉"}</span>{selectedRuntime ? `${selectedRuntime.name} · ${selectedRuntime.model}` : "未配置"}</button>
          {runtimePickerOpen && <div className="chat-template-picker chat-runtime-picker" role="dialog" aria-label="选择模型"><strong>选择入口与模型</strong><div className="chat-runtime-modes" role="tablist"><button type="button" role="tab" aria-selected={pickerKind === "cli"} onClick={() => { setPickerKind("cli"); void loadRuntimeOptions("cli"); }}>本机 CLI</button><button type="button" role="tab" aria-selected={pickerKind === "api"} onClick={() => { setPickerKind("api"); void loadRuntimeOptions("api"); }}>API 提供商</button></div>{runtimeOptions.length === 0 && <span>暂无可用入口，请先在设置中配置。</span>}{runtimeOptions.map((runtime) => <div key={runtime.id}><button type="button" disabled={runtime.models.length === 0} onClick={() => { const model = runtime.models[0] ?? ""; const kind: "cli" | "api" = runtime.kind === "api" ? "api" : "cli"; const next = { id: runtime.id, name: runtime.display_name, model, kind }; setSelectedRuntime(next); workflow?.setExecutionSelection?.(model ? { mode: kind, runtimeId: runtime.id, model } : null); setRuntimePickerOpen(false); }}>{runtime.display_name} · {runtime.models.length} 个模型</button>{runtime.models.slice(0, 8).map((model) => <button type="button" key={`${runtime.id}-${model}`} onClick={() => { const kind: "cli" | "api" = runtime.kind === "api" ? "api" : "cli"; const next = { id: runtime.id, name: runtime.display_name, model, kind }; setSelectedRuntime(next); workflow?.setExecutionSelection?.({ mode: kind, runtimeId: runtime.id, model }); setRuntimePickerOpen(false); }}>　{model}</button>)}</div>)}<button type="button" onClick={() => { setRuntimePickerOpen(false); onOpenSettings?.(); }}>设置</button></div>}
          <textarea value={input} onChange={(event) => setInput(event.currentTarget.value)} placeholder="说说你想怎么调整…" rows={2} disabled={!workflow || state.phase === "requesting"} />
          <button type="submit" className="send" aria-label="发送" disabled={!workflow || !input.trim() || !canSend || state.phase === "requesting"} title={sendHint ?? undefined}>
            <Icon name="arrow-up" />
          </button>
          <small className="chat-privacy-summary">1 张安全代理图 · 供应商：{selectedRuntime?.name ?? providerLabel ?? "未选择"} · 发送元数据</small>
        </form>
      </>}
    </aside>
  );
}
