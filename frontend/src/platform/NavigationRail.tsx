import type { PlatformPage } from "./platformStore";
import { Icon, type IconName } from "./icons";

type NavigationTarget = "home" | Exclude<PlatformPage, "import">;

type NavigationRailProps = {
  collapsed: boolean;
  activeTarget?: NavigationTarget;
  onNavigate(target: NavigationTarget): void;
  onToggle(): void;
};

type NavItem = { target: NavigationTarget; icon: IconName; label: string; count?: string };
type NavGroup = { id: string; title: string; items: readonly NavItem[]; collapsible?: boolean };

// 原型：侧栏按「工作区 / 扩展」分组，收起按钮与「工作区」标签同行靠右。
const GROUPS: readonly NavGroup[] = [
  {
    id: "workspace",
    title: "工作区",
    collapsible: true,
    items: [
      { target: "home", icon: "home", label: "首页" },
      { target: "library", icon: "library", label: "我的图库" },
      { target: "templates", icon: "template", label: "大师模板" },
    ],
  },
  {
    id: "extend",
    title: "扩展",
    items: [
      { target: "skills", icon: "skill", label: "技能" },
      { target: "plugins", icon: "plugin", label: "插件" },
    ],
  },
];

const FOOT: readonly NavItem[] = [
  { target: "settings", icon: "settings", label: "设置与帮助" },
];

export function NavigationRail({ collapsed, activeTarget, onNavigate, onToggle }: NavigationRailProps) {
  const renderItem = (item: NavItem) => {
    const active = activeTarget === item.target;
    return (
      <button
        key={item.target}
        type="button"
        data-active={active}
        aria-current={active ? "page" : undefined}
        title={item.label}
        onClick={() => onNavigate(item.target)}
      >
        <i className="rail-indicator" aria-hidden="true" />
        <span className="ic" aria-hidden="true"><Icon name={item.icon} /></span>
        <span className="rail-label">{item.label}</span>
        {item.count && <span className="rail-count" aria-hidden="true">{item.count}</span>}
      </button>
    );
  };

  return (
    <nav className="navigation-rail" aria-label="全局导航" data-collapsed={collapsed}>
      {GROUPS.map((group) => (
        <div className="rail-group" key={group.id}>
          <div className="rail-group-head">
            <p className="rail-group-title">{group.title}</p>
            {group.collapsible && (
              <button
                className="rail-toggle"
                type="button"
                onClick={onToggle}
                title={collapsed ? "展开侧栏" : "收起侧栏"}
                aria-label={collapsed ? "展开全局导航" : "折叠全局导航"}
              >
                <span className="ic" aria-hidden="true"><Icon name="collapse" /></span>
              </button>
            )}
          </div>
          {group.items.map(renderItem)}
        </div>
      ))}
      <div className="rail-foot">{FOOT.map(renderItem)}</div>
    </nav>
  );
}
