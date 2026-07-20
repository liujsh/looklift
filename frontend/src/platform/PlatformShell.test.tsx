import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import { createPlatformStore } from "./platformStore";
import { PlatformShell } from "./PlatformShell";

const client = {
  recentSessions: vi.fn().mockResolvedValue([]),
} as unknown as LookliftClient;

describe("PlatformShell", () => {
  it("启动显示固定首页、完整导航和标签栏三入口", () => {
    const html = renderToStaticMarkup(
      <PlatformShell client={client} store={createPlatformStore()} engineLabel="测试引擎" />,
    );

    expect(html).toContain("LookLift");
    expect(html).toContain('data-tab-id="home"');
    expect(html).not.toContain('data-tab-id="home" data-closable="true"');
    for (const label of ["首页", "我的图库", "大师模板", "自动化技能", "插件", "设置与帮助"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain('aria-label="新建工作上下文"');
    for (const action of ["添加文件夹", "从设备导入", "快速修图"]) {
      expect(html).toContain(action);
    }
  });

  it("未来页面只展示版本边界说明", () => {
    const store = createPlatformStore();
    store.openPlatform("library", "我的图库");

    const html = renderToStaticMarkup(
      <PlatformShell client={client} store={store} engineLabel="测试引擎" />,
    );

    expect(html).toContain("将在 v2.3-A 提供");
    expect(html).toContain("只索引，不复制原文件");
    expect(html).toContain('data-closable="true"');
    expect(html).not.toContain("128 张");
  });
});
