import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { CloseStudioDialog } from "./CloseStudioDialog";

describe("CloseStudioDialog", () => {
  it("AI 请求阶段只提供停止继续或取消", () => {
    const html = renderToStaticMarkup(
      <CloseStudioDialog title="a.jpg" phase="ai" busy={false} onCancel={vi.fn()} onStop={vi.fn()} onKeep={vi.fn()} onDiscard={vi.fn()} />,
    );

    expect(html).toContain("停止并继续");
    expect(html).toContain("取消");
    expect(html).not.toContain("保留并关闭");
    expect(html).not.toContain("放弃并关闭");
  });

  it("候选阶段提供保留、放弃、取消并展示保存错误", () => {
    const html = renderToStaticMarkup(
      <CloseStudioDialog title="a.jpg" phase="pending" busy error="磁盘已满" onCancel={vi.fn()} onStop={vi.fn()} onKeep={vi.fn()} onDiscard={vi.fn()} />,
    );

    expect(html).toContain("保留并关闭");
    expect(html).toContain("放弃并关闭");
    expect(html).toContain("取消");
    expect(html).toContain("磁盘已满");
    expect(html).toContain("disabled");
  });
});
