import type { WorkspaceTab } from "./platformStore";
import type { FutureEntry } from "./HomePage";

type WorkspaceTabsProps = {
  tabs: readonly WorkspaceTab[];
  activeTabId: string;
  onActivate(id: string): void;
  canClose?(tab: WorkspaceTab): boolean;
  onClose?(id: string): void;
  onQuickEdit?(): Promise<void> | void;
  quickEditBusy?: boolean;
  onFuture(entry: FutureEntry): void;
};

export function WorkspaceTabs({ tabs, activeTabId, onActivate, canClose, onClose, onQuickEdit, quickEditBusy = false, onFuture }: WorkspaceTabsProps) {
  return (
    <header className="workspace-tabs" data-tauri-drag-region>
      <strong className="platform-brand" data-tauri-drag-region>LookLift</strong>
      <div className="tab-list" role="tablist" aria-label="工作上下文">
        {tabs.map((tab) => {
          const closable = Boolean(onClose && canClose?.(tab));
          return (
            <div className="workspace-tab" data-tab-id={tab.id} data-active={tab.id === activeTabId} data-closable={closable} key={tab.id}>
              <button type="button" role="tab" aria-selected={tab.id === activeTabId} onClick={() => onActivate(tab.id)}>{tab.title}</button>
              {closable && <button className="tab-close" type="button" aria-label={`关闭 ${tab.title}`} onClick={() => onClose?.(tab.id)}>×</button>}
            </div>
          );
        })}
      </div>
      <details className="new-context-menu">
        <summary aria-label="新建工作上下文">＋</summary>
        <div>
          <button type="button" onClick={() => onFuture("folder")}>添加文件夹 <small>v2.3-A</small></button>
          <button type="button" onClick={() => onFuture("device")}>从设备导入 <small>v2.3-B</small></button>
          <button type="button" disabled={!onQuickEdit || quickEditBusy} onClick={() => void onQuickEdit?.()}>
            {quickEditBusy ? "正在打开…" : "快速修图"}
          </button>
        </div>
      </details>
    </header>
  );
}
