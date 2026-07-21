import { describe, expect, it, vi } from "vitest";
import { createPlatformStore, type StudioRuntimeLike } from "./platformStore";

function runtime(sessionId: string): StudioRuntimeLike {
  return { sessionId, title: `${sessionId}.jpg`, dispose: vi.fn() };
}

describe("platformStore", () => {
  it("固定首页并从本机偏好恢复导航折叠状态", () => {
    const values = new Map([["looklift.navigation-collapsed", "true"]]);
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };
    const store = createPlatformStore({ storage });

    expect(store.getSnapshot()).toMatchObject({
      activeTabId: "home",
      navigationCollapsed: true,
      tabs: [{ id: "home", kind: "home", title: "首页" }],
    });
    expect(store.removeTab("home")).toBe(false);
    store.setNavigationCollapsed(false);
    expect(values.get("looklift.navigation-collapsed")).toBe("false");
  });

  it("平台页和正式 session 去重并聚焦已有标签", () => {
    const store = createPlatformStore();
    const first = runtime("session-1");
    const duplicate = runtime("session-1");

    store.openPlatform("library", "我的图库");
    store.openPlatform("library", "我的图库");
    store.openStudio(first);
    store.openStudio(duplicate);

    expect(store.getSnapshot().tabs.map((tab) => tab.id)).toEqual([
      "home", "platform:library", "studio:session-1",
    ]);
    expect(store.getSnapshot().activeTabId).toBe("studio:session-1");
    expect(duplicate.dispose).toHaveBeenCalledTimes(1);
    expect(first.dispose).not.toHaveBeenCalled();
  });

  it("多个 Studio 并存且关闭活动标签后聚焦相邻项", () => {
    const store = createPlatformStore();
    const first = runtime("session-1");
    const second = runtime("session-2");
    store.openStudio(first);
    store.openStudio(second);

    expect(store.getSnapshot().tabs).toHaveLength(3);
    expect(store.removeTab("studio:session-2")).toBe(true);
    expect(second.dispose).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().activeTabId).toBe("studio:session-1");
    expect(store.findStudio("session-1")?.runtime).toBe(first);
  });
});
