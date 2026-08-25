import type { PlatformPage } from "./platformStore";
import { Icon, type IconName } from "./icons";

type NavigationTarget = "home" | Exclude<PlatformPage, "import">;

type NavigationRailProps = {
  collapsed: boolean;
  activeTarget?: NavigationTarget;
  onNavigate(target: NavigationTarget): void;
  onToggle(): void;
};

const ITEMS: ReadonlyArray<{ target: NavigationTarget; icon: IconName; label: string }> = [
  { target: "home", icon: "home", label: "首页" },
  { target: "library", icon: "library", label: "我的图库" },
  { target: "templates", icon: "template", label: "大师模板" },
  { target: "automation", icon: "skill", label: "自动化技能" },
  { target: "plugins", icon: "plugin", label: "插件" },
  { target: "runs", icon: "skill", label: "运行恢复" },
  { target: "settings", icon: "settings", label: "设置与帮助" },
];

export function NavigationRail({ collapsed, activeTarget, onNavigate, onToggle }: NavigationRailProps) {
  return (
    <nav className="navigation-rail" aria-label="全局导航" data-collapsed={collapsed}>
      {ITEMS.map((item) => (
        <button
          key={item.target}
          type="button"
          data-active={activeTarget === item.target}
          aria-current={activeTarget === item.target ? "page" : undefined}
          onClick={() => onNavigate(item.target)}
        >
          <span className="ic" aria-hidden="true"><Icon name={item.icon} /></span><span>{item.label}</span>
        </button>
      ))}
      <div className="rail-foot">
        <button className="navigation-toggle" type="button" onClick={onToggle} aria-label={collapsed ? "展开全局导航" : "折叠全局导航"}>
          <span className="ic" aria-hidden="true"><Icon name="collapse" /></span>
          <span>收起侧栏</span>
        </button>
      </div>
    </nav>
  );
}
