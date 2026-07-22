import { useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { LookliftClient } from "../api/client";
import type { ParamContract, SessionSnapshot } from "../api/types";
import { EditorShell } from "../app/EditorShell";
import { createPlatformStore, type PlatformPage, type PlatformStore } from "./platformStore";
import { createStudioRuntime, type StudioRuntime } from "./studioRuntime";
import { HomePage, type FutureEntry } from "./HomePage";
import { NavigationRail } from "./NavigationRail";
import { WorkspaceTabs } from "./WorkspaceTabs";
import { ComingSoonPage } from "./ComingSoonPage";
import { createNeutralAnalysis } from "../panel/contractModel";
import { chooseBrowserImageFile, nativeImageChooser, runQuickEdit } from "./quickEdit";
import { CloseStudioDialog, type CloseDialogPhase } from "./CloseStudioDialog";
import { SettingsPage } from "./SettingsPage";
import { LibraryPage } from "./LibraryPage";

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

type CloseDialogState = {
  tabId: string;
  title: string;
  phase: CloseDialogPhase;
  busy: boolean;
  error: string | null;
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
  const [closeDialog, setCloseDialog] = useState<CloseDialogState | null>(null);
  const closeActionRunning = useRef(false);
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
  const closeRuntime = () => {
    if (!closeDialog) return null;
    const tab = store.getSnapshot().tabs.find((candidate) => candidate.id === closeDialog.tabId);
    return tab?.kind === "studio" ? tab.runtime as StudioRuntime : null;
  };
  const requestClose = (id: string) => {
    if (closeActionRunning.current) return;
    const tab = store.getSnapshot().tabs.find((candidate) => candidate.id === id);
    if (!tab || tab.kind === "home") return;
    if (tab.kind === "platform") {
      store.removeTab(id);
      return;
    }
    const runtime = tab.runtime as StudioRuntime;
    const requirement = runtime.closeRequirement();
    if (requirement === "direct") store.removeTab(id);
    else setCloseDialog({ tabId: id, title: tab.title, phase: requirement, busy: false, error: null });
  };
  const runCloseAction = async (action: (runtime: StudioRuntime) => Promise<"closed" | "pending">) => {
    if (!closeDialog || closeActionRunning.current) return;
    const runtime = closeRuntime();
    if (!runtime) {
      setCloseDialog(null);
      return;
    }
    closeActionRunning.current = true;
    setCloseDialog((current) => current ? { ...current, busy: true, error: null } : current);
    try {
      const result = await action(runtime);
      if (result === "closed") {
        store.removeTab(closeDialog.tabId);
        setCloseDialog(null);
      } else {
        setCloseDialog((current) => current ? { ...current, phase: "pending", busy: false } : current);
      }
    } catch (reason) {
      setCloseDialog((current) => current ? {
        ...current,
        busy: false,
        error: reason instanceof Error ? reason.message : String(reason),
      } : current);
    } finally {
      closeActionRunning.current = false;
    }
  };

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
        canClose={(tab) => tab.kind !== "home"}
        onClose={requestClose}
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
      <section className="platform-content" inert={closeDialog ? true : undefined}>
        {shellError && <div className="platform-error" role="alert">{shellError}</div>}
        {activeTab.kind === "home" && <HomePage client={client} onResume={resume} onQuickEdit={quickEdit} quickEditBusy={quickEditBusy} onFuture={openFuture} />}
        {activeTab.kind === "platform" && (activeTab.page === "settings" ? <SettingsPage client={client} /> : activeTab.page === "library" ? <LibraryPage client={client} onOpen={async (path) => {
          if (!contract) throw new Error("参数契约尚未就绪");
          openSnapshot(await client.createSession({ path, initial_analysis: createNeutralAnalysis(contract) }));
        }} /> : <ComingSoonPage page={activeTab.page} />)}
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
              coordinator={runtime.coordinator}
              workflow={runtime.workflow}
            />
          </div>;
        })}
      </section>
      {closeDialog && <CloseStudioDialog
        title={closeDialog.title}
        phase={closeDialog.phase}
        busy={closeDialog.busy}
        error={closeDialog.error}
        onCancel={() => {
          if (!closeActionRunning.current) setCloseDialog(null);
        }}
        onStop={() => runCloseAction(async (runtime) => runtime.stopAiForClose() === "pending" ? "pending" : "closed")}
        onKeep={() => runCloseAction(async (runtime) => {
          await runtime.resolvePendingForClose("keep");
          return "closed";
        })}
        onDiscard={() => runCloseAction(async (runtime) => {
          await runtime.resolvePendingForClose("discard");
          return "closed";
        })}
      />}
      <aside className="window-width-warning" role="status">
        <strong>需要更宽的工作区</strong>
        <span>请将窗口增大到至少 880px，以完整使用画布和调整面板。</span>
      </aside>
    </main>
  );
}
