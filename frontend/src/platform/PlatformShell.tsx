import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { LookliftClient } from "../api/client";
import type { ParamContract, SessionSnapshot } from "../api/types";
import { EditorShell } from "../app/EditorShell";
import { createPlatformStore, type PlatformPage, type PlatformStore } from "./platformStore";
import { createStudioRuntime } from "./studioRuntime";
import { HomePage, type FutureEntry } from "./HomePage";
import { NavigationRail } from "./NavigationRail";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { ComingSoonPage } from "./ComingSoonPage";
import { createNeutralAnalysis } from "../panel/contractModel";
import { chooseBrowserImageFile, nativeImageChooser, runQuickEdit } from "./quickEdit";

type PlatformShellProps = {
  client: LookliftClient;
  contract?: ParamContract;
  engineLabel?: string;
  store?: PlatformStore;
  onQuickEdit?(): Promise<void> | void;
};

const PLATFORM_TITLES: Record<PlatformPage, string> = {
  library: "我的图库",
  import: "从设备导入",
  templates: "大师模板",
  automation: "自动化技能",
  plugins: "插件",
  settings: "设置与帮助",
};

function localStorageOrUndefined(): Storage | undefined {
  try { return typeof window === "undefined" ? undefined : window.localStorage; } catch { return undefined; }
}

export function PlatformShell({ client, contract, engineLabel, store: providedStore, onQuickEdit }: PlatformShellProps) {
  const ownedStore = useMemo(() => createPlatformStore({ storage: localStorageOrUndefined() }), []);
  const store = providedStore ?? ownedStore;
  const platform = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [shellError, setShellError] = useState<string | null>(null);
  const [quickEditBusy, setQuickEditBusy] = useState(false);
  const quickEditRunning = useRef(false);
  const activeTab = platform.tabs.find((tab) => tab.id === platform.activeTabId) ?? platform.tabs[0];

  const openPage = (page: PlatformPage) => store.openPlatform(page, PLATFORM_TITLES[page]);
  const openFuture = (entry: FutureEntry) => openPage(entry === "folder" ? "library" : "import");
  const openSnapshot = (snapshot: SessionSnapshot) => {
    const existing = store.findStudio(snapshot.id);
    if (existing) store.activateTab(existing.id);
    else store.openStudio(createStudioRuntime(client, snapshot));
  };
  const resume = async (sessionId: string) => {
    setShellError(null);
    const existing = store.findStudio(sessionId);
    if (existing) {
      store.activateTab(existing.id);
      return;
    }
    openSnapshot(await client.getSession(sessionId));
  };
  const quickEdit = contract || onQuickEdit ? async () => {
    if (quickEditRunning.current) return;
    quickEditRunning.current = true;
    setQuickEditBusy(true);
    setShellError(null);
    try {
      if (onQuickEdit) {
        await onQuickEdit();
      } else if (contract) {
        await runQuickEdit({
          initialAnalysis: createNeutralAnalysis(contract),
          chooseNativePath: nativeImageChooser(),
          chooseBrowserFile: chooseBrowserImageFile,
          upload: (file) => client.upload(file),
          createSession: (payload) => client.createSession(payload),
          openSession: openSnapshot,
        });
      }
    } catch (reason) {
      setShellError(`快速修图启动失败：${reason instanceof Error ? reason.message : String(reason)}`);
    } finally {
      quickEditRunning.current = false;
      setQuickEditBusy(false);
    }
  } : undefined;

  const activeTarget = activeTab.kind === "home"
    ? "home"
    : activeTab.kind === "platform" && activeTab.page !== "import" ? activeTab.page : undefined;
  const navigationCollapsed = activeTab.kind === "studio" ? true : platform.navigationCollapsed;

  return (
    <main className="platform-shell" data-navigation-collapsed={navigationCollapsed}>
      <WorkspaceTabs
        tabs={platform.tabs}
        activeTabId={platform.activeTabId}
        onActivate={store.activateTab}
        canClose={(tab) => tab.kind === "platform"}
        onClose={store.removeTab}
        onQuickEdit={quickEdit}
        quickEditBusy={quickEditBusy}
        onFuture={openFuture}
      />
      <NavigationRail
        collapsed={navigationCollapsed}
        activeTarget={activeTarget}
        onToggle={() => store.setNavigationCollapsed(!platform.navigationCollapsed)}
        onNavigate={(target) => target === "home" ? store.activateTab("home") : openPage(target)}
      />
      <section className="platform-content">
        {shellError && <div className="platform-error" role="alert">{shellError}</div>}
        {activeTab.kind === "home" && <HomePage client={client} onResume={resume} onQuickEdit={quickEdit} quickEditBusy={quickEditBusy} onFuture={openFuture} />}
        {activeTab.kind === "platform" && <ComingSoonPage page={activeTab.page} />}
        {platform.tabs.filter((tab) => tab.kind === "studio").map((tab) => {
          const active = tab.id === platform.activeTabId;
          const runtime = tab.runtime as ReturnType<typeof createStudioRuntime>;
          return <div className="studio-tab-content" hidden={!active} key={tab.id}>
            <EditorShell
              store={runtime.store}
              active={active}
              client={client}
              contract={contract}
              engineLabel={engineLabel}
            />
          </div>;
        })}
      </section>
    </main>
  );
}
