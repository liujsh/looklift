import type { PlatformPage } from "./platformStore";

type NavigationTarget = "home" | Exclude<PlatformPage, "import">;

type NavigationRailProps = {
  collapsed: boolean;
  activeTarget?: NavigationTarget;
  onNavigate(target: NavigationTarget): void;
  onToggle(): void;
};

const ITEMS: ReadonlyArray<{ target: NavigationTarget; icon: string; label: string }> = [
  { target: "home", icon: "⌂", label: "首页" },
  { target: "library", icon: "▱", label: "我的图库" },
  { target: "templates", icon: "◈", label: "大师模板" },
  { target: "automation", icon: "⚡", label: "自动化技能" },
  { target: "plugins", icon: "◇", label: "插件" },
  { target: "settings", icon: "⚙", label: "设置与帮助" },
];

export function NavigationRail({ collapsed, activeTarget, onNavigate, onToggle }: NavigationRailProps) {
  return (
    <nav className="navigation-rail" aria-label="全局导航" data-collapsed={collapsed}>
      <button className="navigation-toggle" type="button" onClick={onToggle} aria-label={collapsed ? "展开全局导航" : "折叠全局导航"}>
        {collapsed ? "›" : "‹"}
      </button>
      {ITEMS.map((item) => (
        <button
          key={item.target}
          type="button"
          data-active={activeTarget === item.target}
          aria-current={activeTarget === item.target ? "page" : undefined}
          onClick={() => onNavigate(item.target)}
        >
          <span aria-hidden="true">{item.icon}</span><span>{item.label}</span>
        </button>
      ))}
    </nav>
  );
}
