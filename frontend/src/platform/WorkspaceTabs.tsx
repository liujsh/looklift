import type { WorkspaceTab } from "./platformStore";
import type { FutureEntry } from "./HomePage";
import { BrandLogo, Icon } from "./icons";

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

// 原型：圆角胶囊标签 + 状态点 + 悬停关闭；品牌标只出现在这一处。
export function WorkspaceTabs({ tabs, activeTabId, onActivate, canClose, onClose, onQuickEdit, quickEditBusy = false, onFuture }: WorkspaceTabsProps) {
  return (
    <header className="workspace-tabs" data-tauri-drag-region>
      <strong className="platform-brand" data-tauri-drag-region><BrandLogo />LookLift</strong>
      <div className="tab-list" role="tablist" aria-label="工作上下文">
        {tabs.map((tab) => {
          const closable = Boolean(onClose && canClose?.(tab));
          const active = tab.id === activeTabId;
          return (
            <div className="workspace-tab" data-tab-id={tab.id} data-active={active} data-closable={closable} key={tab.id}>
              <button type="button" role="tab" aria-selected={active} onClick={() => onActivate(tab.id)}>
                <i className="tab-dot" aria-hidden="true" />
                <span>{tab.title}</span>
              </button>
              {closable && (
                <button className="tab-close" type="button" aria-label={`关闭 ${tab.title}`} onClick={() => onClose?.(tab.id)}>
                  <Icon name="close" />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <details className="new-context-menu">
        <summary aria-label="新建工作上下文" title="新建工作上下文"><Icon name="add" /></summary>
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
