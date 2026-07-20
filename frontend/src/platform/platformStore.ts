export type PlatformPage = "library" | "import" | "templates" | "automation" | "plugins" | "settings";

export type StudioRuntimeLike = {
  sessionId: string;
  title: string;
  dispose(): void;
};

export type HomeTab = Readonly<{ id: "home"; kind: "home"; title: "首页" }>;
export type PlatformTab = Readonly<{
  id: `platform:${PlatformPage}`;
  kind: "platform";
  title: string;
  page: PlatformPage;
}>;
export type StudioTab = Readonly<{
  id: `studio:${string}`;
  kind: "studio";
  title: string;
  sessionId: string;
  runtime: StudioRuntimeLike;
}>;
export type WorkspaceTab = HomeTab | PlatformTab | StudioTab;

export type PlatformState = Readonly<{
  tabs: readonly WorkspaceTab[];
  activeTabId: string;
  navigationCollapsed: boolean;
}>;

type StorageLike = Pick<Storage, "getItem" | "setItem">;
type PlatformStoreOptions = { storage?: StorageLike };

export type PlatformStore = {
  getSnapshot(): PlatformState;
  subscribe(listener: () => void): () => void;
  setNavigationCollapsed(collapsed: boolean): void;
  openPlatform(page: PlatformPage, title: string): PlatformTab;
  openStudio(runtime: StudioRuntimeLike): StudioTab;
  activateTab(id: string): boolean;
  removeTab(id: string): boolean;
  findStudio(sessionId: string): StudioTab | undefined;
};

const NAVIGATION_KEY = "looklift.navigation-collapsed";
const HOME_TAB: HomeTab = Object.freeze({ id: "home", kind: "home", title: "首页" });

function initialCollapsed(storage?: StorageLike): boolean {
  try {
    return storage?.getItem(NAVIGATION_KEY) === "true";
  } catch {
    return false;
  }
}

export function createPlatformStore(options: PlatformStoreOptions = {}): PlatformStore {
  let state: PlatformState = Object.freeze({
    tabs: Object.freeze([HOME_TAB]),
    activeTabId: HOME_TAB.id,
    navigationCollapsed: initialCollapsed(options.storage),
  });
  const listeners = new Set<() => void>();

  const publish = (patch: Partial<PlatformState>) => {
    state = Object.freeze({ ...state, ...patch });
    for (const listener of listeners) listener();
  };

  const findStudio = (sessionId: string) => state.tabs.find(
    (tab): tab is StudioTab => tab.kind === "studio" && tab.sessionId === sessionId,
  );

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setNavigationCollapsed(collapsed) {
      if (collapsed === state.navigationCollapsed) return;
      try { options.storage?.setItem(NAVIGATION_KEY, String(collapsed)); } catch { /* 偏好写入失败不阻断修图。 */ }
      publish({ navigationCollapsed: collapsed });
    },
    openPlatform(page, title) {
      const id = `platform:${page}` as const;
      const existing = state.tabs.find((tab): tab is PlatformTab => tab.id === id);
      if (existing) {
        publish({ activeTabId: id });
        return existing;
      }
      const tab: PlatformTab = Object.freeze({ id, kind: "platform", title, page });
      publish({ tabs: Object.freeze([...state.tabs, tab]), activeTabId: id });
      return tab;
    },
    openStudio(runtime) {
      const existing = findStudio(runtime.sessionId);
      if (existing) {
        runtime.dispose();
        publish({ activeTabId: existing.id });
        return existing;
      }
      const tab: StudioTab = Object.freeze({
        id: `studio:${runtime.sessionId}`,
        kind: "studio",
        title: runtime.title,
        sessionId: runtime.sessionId,
        runtime,
      });
      publish({ tabs: Object.freeze([...state.tabs, tab]), activeTabId: tab.id });
      return tab;
    },
    activateTab(id) {
      if (!state.tabs.some((tab) => tab.id === id)) return false;
      if (state.activeTabId !== id) publish({ activeTabId: id });
      return true;
    },
    removeTab(id) {
      if (id === HOME_TAB.id) return false;
      const index = state.tabs.findIndex((tab) => tab.id === id);
      if (index < 0) return false;
      const removed = state.tabs[index];
      if (removed.kind === "studio") removed.runtime.dispose();
      const tabs = state.tabs.filter((tab) => tab.id !== id);
      const activeTabId = state.activeTabId === id
        ? tabs[Math.min(index, tabs.length - 1)].id
        : state.activeTabId;
      publish({ tabs: Object.freeze(tabs), activeTabId });
      return true;
    },
    findStudio,
  };
}
