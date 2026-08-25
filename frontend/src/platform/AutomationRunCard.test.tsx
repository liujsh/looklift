import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { AutomationRun } from "../api/types";
import { AutomationRunCard } from "./AutomationRunCard";

const run: AutomationRun = {
  id: "run-1",
  plan_id: "plan-1",
  workflow: {
    id: "workflow-1", name: "胶片批处理", look_name: "柔和胶片", factor: .8,
    suffix: "-film", quality: 92, created_at: "2026-07-24",
  },
  status: "done",
  created_at: "2026-07-24",
  updated_at: "2026-07-24",
  total: 2,
  completed: 1,
  failed: 1,
  cancelled: 0,
  items: [
    { source: "C:/照片/正常.jpg", output: "C:/输出/正常-film.jpg", status: "completed", error: null },
    { source: "C:/照片/损坏.jpg", output: "C:/输出/损坏-film.jpg", status: "failed", error: "无法解码图片" },
  ],
};

describe("AutomationRunCard", () => {
  it("活动运行展示失败文件、原因和定向重试", () => {
    const html = renderToStaticMarkup(
      <AutomationRunCard run={run} active onRetry={vi.fn()} />,
    );

    expect(html).toContain("损坏.jpg");
    expect(html).toContain("无法解码图片");
    expect(html).toContain("只重试失败项");
    expect(html).not.toContain("正常.jpg");
  });

  it("全部成功时明确说明原照片未改变", () => {
    const completed = {
      ...run,
      failed: 0,
      completed: 2,
      items: run.items.map((item) => ({ ...item, status: "completed" as const, error: null })),
    };

    expect(renderToStaticMarkup(<AutomationRunCard run={completed} active />))
      .toContain("全部成片已生成，原照片未改变");
  });
});
