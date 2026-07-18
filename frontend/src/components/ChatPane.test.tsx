import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ChatWorkflow, ChatWorkflowState } from "../features/chat/chatWorkflow";
import type { SessionCoordinator } from "../features/sessions/sessionCoordinator";
import { ChatPane, submitChatInput } from "./ChatPane";

function workflow(state: Partial<ChatWorkflowState> = {}): ChatWorkflow {
  const snapshot: ChatWorkflowState = {
    phase: "idle", messages: [], lastResponse: null, error: null, round: 0, stopReason: null,
    ...state,
  };
  return {
    getSnapshot: () => snapshot, subscribe: () => () => {}, send: vi.fn(), refine: vi.fn(),
    cancel: vi.fn(), setIncludeMetadata: vi.fn(), restoreMessages: vi.fn(), settlePending: vi.fn(),
  };
}

const coordinator = {
  acceptPending: vi.fn(), discardPending: vi.fn(), continueManual: vi.fn(), recordMessages: vi.fn(),
  commitFormal: vi.fn(), open: vi.fn(), getSessionId: () => "s1",
} as SessionCoordinator;

describe("ChatPane", () => {
  it("空态包含输入、附件 seam、隐私摘要和折叠入口", () => {
    const html = renderToStaticMarkup(<ChatPane enabled workflow={workflow()} coordinator={coordinator} providerLabel="ollama" />);
    expect(html).toContain("说说你想怎么调整");
    expect(html).toContain('aria-label="添加附件或模板"');
    expect(html).toContain("1 张安全代理图");
    expect(html).toContain("供应商：ollama");
    expect(html).toContain("发送元数据");
    expect(html).toContain('aria-label="折叠 AI 对话"');
  });

  it("呈现消息、变化记录、能力边界和 pending 动作", () => {
    const html = renderToStaticMarkup(<ChatPane enabled workflow={workflow({
      phase: "pending",
      messages: [{ role: "user", content: "只提亮人物" }, { role: "assistant", content: "先做全局近似" }],
      lastResponse: {
        analysis: {} as never,
        changes: [{ path: "basic.exposure", before: 0, after: 0.4 }], rejected: [],
        explanation: "先做全局近似", limitations: ["当前不能自动完成局部蒙版"],
        approximation: "用全局曝光近似", manual_steps: ["在右侧面板把曝光设为 +0.4"],
        done: false, provider: "mock", proxy_count: 1, metadata_sent: true,
      },
    })} coordinator={coordinator} />);
    expect(html).toContain("只提亮人物");
    expect(html).toContain("basic.exposure");
    expect(html).toContain("当前不能自动完成");
    expect(html).toContain("可用近似方案");
    expect(html).toContain("右侧面板手动步骤");
    expect(html).toContain("保留此版本");
    expect(html).toContain("撤销");
    expect(html).toContain("AI 精修");
    expect(html).toContain("继续手调");
  });

  it("候选预览完成前只允许撤销并显示渲染提示", () => {
    const html = renderToStaticMarkup(<ChatPane
      enabled
      workflow={workflow({ phase: "pending" })}
      coordinator={coordinator}
      renderStatus="rendering"
    />);
    expect(html).toContain("正在渲染候选预览");
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>保留此版本<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>AI 精修<\/button>/);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>继续手调<\/button>/);
    expect(html).toMatch(/<button(?![^>]*disabled)[^>]*>撤销<\/button>/);
  });

  it("两轮精修完成后禁用精修按钮", () => {
    const html = renderToStaticMarkup(<ChatPane
      enabled
      workflow={workflow({ phase: "pending", round: 2, stopReason: "round_limit" })}
      coordinator={coordinator}
      renderStatus="ready"
    />);
    expect(html).toMatch(/<button[^>]*disabled=""[^>]*>AI 精修<\/button>/);
  });

  it("发送中区分初次请求与精修轮次，错误提供稳定出口", () => {
    const initial = renderToStaticMarkup(<ChatPane enabled workflow={workflow({ phase: "requesting", round: 0 })} coordinator={coordinator} />);
    expect(initial).toContain("正在分析修图要求");
    expect(initial).toContain("取消");
    const refining = renderToStaticMarkup(<ChatPane enabled workflow={workflow({ phase: "requesting", round: 1 })} coordinator={coordinator} />);
    expect(refining).toContain("AI 精修第 1/2 轮");
    const failed = renderToStaticMarkup(<ChatPane enabled workflow={workflow({ phase: "error", error: "服务未启动" })} coordinator={coordinator} />);
    expect(failed).toContain("服务未启动");
    expect(failed).toContain("重试或继续手调");
  });

  it("提交助手会清理空白并调用单轮 send", async () => {
    const current = workflow();
    await submitChatInput("  提亮一点  ", current);
    expect(current.send).toHaveBeenCalledWith("提亮一点");
  });
});
