import { useSyncExternalStore, useState } from "react";
import type { ChatWorkflow } from "../features/chat/chatWorkflow";
import type { SessionCoordinator } from "../features/sessions/sessionCoordinator";
import { ChatChangeCard } from "./ChatChangeCard";
import { ChatMessageList } from "./ChatMessageList";

type ChatPaneProps = {
  enabled: boolean;
  workflow?: ChatWorkflow | null;
  coordinator?: SessionCoordinator | null;
  providerLabel?: string;
};

export async function submitChatInput(value: string, workflow: ChatWorkflow) {
  const message = value.trim();
  if (!message) return null;
  return workflow.send(message);
}

const EMPTY = Object.freeze({
  phase: "idle" as const, messages: Object.freeze([]), lastResponse: null,
  error: null, round: 0, stopReason: null,
});
const emptySubscribe = () => () => {};

export function ChatPane({ enabled, workflow, coordinator, providerLabel = "当前配置" }: ChatPaneProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [input, setInput] = useState("");
  const [includeMetadata, setIncludeMetadata] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);
  const state = useSyncExternalStore(
    workflow?.subscribe ?? emptySubscribe,
    workflow?.getSnapshot ?? (() => EMPTY),
    workflow?.getSnapshot ?? (() => EMPTY),
  );
  const response = state.lastResponse;
  const act = async (action: () => Promise<unknown>) => {
    setActionError(null);
    setActionBusy(true);
    try { await action(); } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally { setActionBusy(false); }
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
          <button type="button" disabled={actionBusy} className="primary" onClick={() => void act(async () => {
            await (coordinator?.acceptPending() ?? Promise.reject(new Error("会话尚未就绪")));
            workflow?.settlePending();
          })}>保留此版本</button>
          <button type="button" disabled={actionBusy} onClick={() => void act(async () => {
            await (coordinator?.discardPending() ?? Promise.reject(new Error("会话尚未就绪")));
            workflow?.settlePending();
          })}>撤销</button>
          <button type="button" disabled={actionBusy} onClick={() => void act(() => workflow?.refine() ?? Promise.reject(new Error("AI 尚未就绪")))}>AI 精修</button>
          <button type="button" disabled={actionBusy} onClick={() => void act(async () => {
            await (coordinator?.continueManual() ?? Promise.reject(new Error("会话尚未就绪")));
            workflow?.settlePending();
          })}>继续手调</button>
        </div>}

        {state.phase === "requesting" && <div className="chat-progress" aria-live="polite">
          <span>第 {Math.max(1, state.round)}/2 轮 · 正在分析</span>
          <button type="button" onClick={() => workflow?.cancel()}>取消等待</button>
        </div>}

        <form className="chat-composer" onSubmit={(event) => {
          event.preventDefault();
          if (!workflow || !input.trim()) return;
          const value = input;
          setInput("");
          void act(async () => {
            const result = await submitChatInput(value, workflow);
            void result;
          });
        }}>
          <button type="button" aria-label="添加附件或模板" title="添加照片、模板或自动化技能">+</button>
          <textarea value={input} onChange={(event) => setInput(event.currentTarget.value)} placeholder="描述想要的颜色、光线或氛围" rows={2} disabled={!workflow || state.phase === "requesting"} />
          <button type="submit" className="send" disabled={!workflow || !input.trim() || state.phase === "requesting"}>发送</button>
        </form>
      </>}
    </aside>
  );
}
