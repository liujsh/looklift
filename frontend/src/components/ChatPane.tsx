import { useSyncExternalStore, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { Analysis, TemplateCard } from "../api/types";
import type { ChatWorkflow } from "../features/chat/chatWorkflow";
import type { SessionCoordinator } from "../features/sessions/sessionCoordinator";
import type { RenderStatus } from "../store/editorStore";
import { ChatChangeCard } from "./ChatChangeCard";
import { ChatMessageList } from "./ChatMessageList";

type ChatPaneProps = {
  enabled: boolean;
  workflow?: ChatWorkflow | null;
  coordinator?: SessionCoordinator | null;
  providerLabel?: string;
  renderStatus?: RenderStatus;
  client?: LookliftClient;
};

export type TemplatePromptAttachment = { template: TemplateCard; analysis: Analysis };

export function buildTemplatePrompt(message: string, attachment?: TemplatePromptAttachment | null): string {
  if (!attachment) return message;
  return [
    `用户要求：${message}`,
    `参考模板：${attachment.template.name}（${attachment.template.summary}）`,
    `模板白盒参数：${JSON.stringify(attachment.analysis)}`,
    "请结合当前照片自适应这些参数，不要机械覆盖；只修改现有白盒参数契约允许的字段。",
  ].join("\n");
}

export async function submitChatInput(
  value: string, workflow: ChatWorkflow, attachment?: TemplatePromptAttachment | null,
) {
  const message = value.trim();
  if (!message) return null;
  return workflow.send(buildTemplatePrompt(message, attachment));
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
  providerLabel = "当前配置",
  renderStatus = "ready",
  client,
}: ChatPaneProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [input, setInput] = useState("");
  const [includeMetadata, setIncludeMetadata] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
  const [templates, setTemplates] = useState<readonly TemplateCard[]>([]);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [attachment, setAttachment] = useState<TemplatePromptAttachment | null>(null);
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
    const next = !templatePickerOpen;
    setTemplatePickerOpen(next);
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
      setTemplatePickerOpen(false);
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
        <div><p className="pane-kicker">AI Studio</p><h2>对话修图</h2></div>
        <button type="button" aria-label={collapsed ? "展开 AI 对话" : "折叠 AI 对话"} onClick={() => setCollapsed(!collapsed)}>
          {collapsed ? "›" : "‹"}
        </button>
      </header>
      {!collapsed && <>
        <section className="chat-privacy" aria-label="调用隐私摘要">
          <span>供应商：{response?.provider ?? providerLabel}</span>
          <span>{response?.proxy_count ?? 1} 张安全代理图</span>
          <label><input type="checkbox" checked={includeMetadata} onChange={(event) => {
            setIncludeMetadata(event.currentTarget.checked);
            workflow?.setIncludeMetadata(event.currentTarget.checked);
          }} />发送元数据</label>
        </section>

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
          const value = input;
          setInput("");
          void act(async () => {
            const result = await submitChatInput(value, workflow, attachment);
            if (result) setAttachment(null);
            void result;
          });
        }}>
          {attachment && <div className="chat-template-chip">
            <span>模板 · {attachment.template.name}</span>
            <button type="button" aria-label="移除模板附件" onClick={() => setAttachment(null)}>×</button>
          </div>}
          {templatePickerOpen && <div className="chat-template-picker" role="dialog" aria-label="选择模板附件">
            <strong>选择模板作为 AI 参考</strong>
            {templates.map((template) => <button type="button" key={template.name} onClick={() => void selectTemplate(template)}>
              <span>{template.name}</span><small>{template.summary}</small>
            </button>)}
            {templateLoading && <span>正在载入模板…</span>}
          </div>}
          <button type="button" aria-label="添加附件或模板" title="添加模板" disabled={!client} onClick={() => void toggleTemplatePicker()}>+</button>
          <textarea value={input} onChange={(event) => setInput(event.currentTarget.value)} placeholder="说说你想怎么调整" rows={2} disabled={!workflow || state.phase === "requesting"} />
          <button type="submit" className="send" disabled={!workflow || !input.trim() || state.phase === "requesting"}>发送</button>
        </form>
      </>}
    </aside>
  );
}
