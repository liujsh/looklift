// 线性图标集：24×24 网格、stroke 1.75、round cap/join，逐条对齐原型 LookLift 界面优化.dc.html。
export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <defs>
        {/* 导航 */}
        <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 11l9-7 9 7" /><path d="M5 9.5V20h14V9.5" /><path d="M10 20v-5h4v5" /></symbol>
        <symbol id="i-library" viewBox="0 0 24 24"><rect x="7" y="4" width="13" height="13" rx="2" /><path d="M4 8v11a1 1 0 0 0 1 1h11" /><circle cx="11.5" cy="8.2" r="1.2" /><path d="M8 14.5l2.6-2.6 2 2 3-3.4 2.4 2.6" /></symbol>
        <symbol id="i-template" viewBox="0 0 24 24"><path d="M12 3l8 4.5-8 4.5-8-4.5z" /><path d="M4 12l8 4.5 8-4.5" /><path d="M4 16.3l8 4.5 8-4.5" /></symbol>
        <symbol id="i-skill" viewBox="0 0 24 24"><path d="M13 3L5 13.5h5l-1 7.5L18 10h-5z" /></symbol>
        <symbol id="i-plugin" viewBox="0 0 24 24"><path d="M10 4a1.6 1.6 0 0 1 3.1 0c0 .9.6 1.1 1.2 1.1H16a1 1 0 0 1 1 1v1.7c0 .6.2 1.2 1.1 1.2a1.6 1.6 0 0 1 0 3.1c-.9 0-1.1.6-1.1 1.2V16a1 1 0 0 1-1 1h-1.7c-.6 0-1.2.2-1.2 1.1a1.6 1.6 0 0 1-3.1 0c0-.9-.6-1.1-1.2-1.1H6a1 1 0 0 1-1-1v-1.8c0-.6-.2-1.2-1.1-1.2a1.6 1.6 0 0 1 0-3.1c.9 0 1.1-.6 1.1-1.2V6a1 1 0 0 1 1-1h1.8c.6 0 1.2-.2 1.2-1.1z" /></symbol>
        <symbol id="i-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.2" /><path d="M12 2v2.6M12 19.4V22M2 12h2.6M19.4 12H22M5.1 5.1l1.9 1.9M17 17l1.9 1.9M18.9 5.1L17 7M7 17l-1.9 1.9" /></symbol>

        {/* 首页动作 */}
        <symbol id="i-aperture" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 3l4.6 8M21 12h-9.2M16.6 16.9L12 9M12 21l-4.6-8M3 12h9.2M7.4 7.1L12 15" /></symbol>
        <symbol id="i-folder-plus" viewBox="0 0 24 24"><path d="M4 7a1 1 0 0 1 1-1h4.6l2 2H19a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /><path d="M12 11.4v5M9.5 13.9h5" /></symbol>
        <symbol id="i-import" viewBox="0 0 24 24"><path d="M12 2.5v8M8.6 7.6L12 11l3.4-3.4" /><rect x="3" y="14" width="18" height="6" rx="2" /><path d="M7 17h.01M11 17h.01" /></symbol>
        <symbol id="i-relocate" viewBox="0 0 24 24"><path d="M12 21s7-5.8 7-11a7 7 0 1 0-14 0c0 5.2 7 11 7 11z" /><circle cx="12" cy="10" r="2.5" /></symbol>

        {/* 通用控件 */}
        <symbol id="i-arrow-right" viewBox="0 0 24 24"><path d="M4 12h14M13 6l6 6-6 6" /></symbol>
        <symbol id="i-arrow-up" viewBox="0 0 24 24"><path d="M12 20V5M6 11l6-6 6 6" /></symbol>
        <symbol id="i-arrow-up-right" viewBox="0 0 24 24"><path d="M7 17L17 7M8.5 7H17v8.5" /></symbol>
        <symbol id="i-check" viewBox="0 0 24 24"><path d="M2 13l4 4 8-8M12.5 15.5L15 18l7-7" /></symbol>
        <symbol id="i-collapse" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9.5 4v16" /></symbol>
        <symbol id="i-close" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></symbol>
        <symbol id="i-add" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></symbol>
        <symbol id="i-min" viewBox="0 0 24 24"><path d="M5 12h14" /></symbol>
        <symbol id="i-max" viewBox="0 0 24 24"><path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" /></symbol>
        <symbol id="i-chevron-down" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6" /></symbol>
        <symbol id="i-chevron-left" viewBox="0 0 24 24"><path d="M15 6l-6 6 6 6" /></symbol>
        <symbol id="i-chevron-right" viewBox="0 0 24 24"><path d="M9 6l6 6-6 6" /></symbol>
        <symbol id="i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 11v5M12 8.2h.01" /></symbol>
        <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 3v11M8 10.5l4 4 4-4M4 17v2a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-2" /></symbol>
        <symbol id="i-reset" viewBox="0 0 24 24"><path d="M4.8 9.2A7.5 7.5 0 1 1 4.5 14" /><path d="M4.2 4.6v4.8h4.8" /></symbol>

        {/* 图库 */}
        <symbol id="i-search" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5" /><path d="M20 20l-4.3-4.3" /></symbol>
        <symbol id="i-folder" viewBox="0 0 24 24"><path d="M4 7a1 1 0 0 1 1-1h4.6l2 2H19a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /></symbol>
        <symbol id="i-folder-search" viewBox="0 0 24 24"><path d="M4 7a1 1 0 0 1 1-1h4.6l2 2H19a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /><circle cx="12.4" cy="13" r="2.4" /><path d="M14.3 14.9L16 16.6" /></symbol>
        <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M4.5 12a7.5 7.5 0 0 1 13-5.2M19.5 12a7.5 7.5 0 0 1-13 5.2" /><path d="M17.5 4.6v3.6h-3.6M6.5 19.4v-3.6h3.6" /></symbol>
        <symbol id="i-trash" viewBox="0 0 24 24"><path d="M4.5 7h15" /><path d="M9.5 7V5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v2" /><path d="M6.5 7l1 12.5a1 1 0 0 0 1 .9h7a1 1 0 0 0 1-.9L17.5 7" /><path d="M10.3 11v6M13.7 11v6" /></symbol>
        <symbol id="i-reveal" viewBox="0 0 24 24"><path d="M4 7a1 1 0 0 1 1-1h4.2l1.8 2H19a1 1 0 0 1 1 1v1.5H4z" /><path d="M4 10.5h16.4l-1.6 7.7a1 1 0 0 1-1 .8H6.6a1 1 0 0 1-1-.8z" /></symbol>
        <symbol id="i-tag" viewBox="0 0 24 24"><path d="M3.5 12.4V5.5a2 2 0 0 1 2-2h6.9a2 2 0 0 1 1.4.6l6.1 6.1a1.6 1.6 0 0 1 0 2.3l-6 6a1.6 1.6 0 0 1-2.3 0L4.1 13.8a2 2 0 0 1-.6-1.4z" /><circle cx="8" cy="8" r="1.4" /></symbol>
        <symbol id="i-drive" viewBox="0 0 24 24"><rect x="3" y="7" width="18" height="10" rx="2" /><path d="M3 12.5h18M7 15h.01M11 15h.01" /></symbol>

        {/* Studio 画布 */}
        <symbol id="i-image" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><circle cx="8.6" cy="9.4" r="1.4" /><path d="M4 18l5-5 3.5 3.5L16 13l4 4" /></symbol>
        <symbol id="i-image-plus" viewBox="0 0 24 24"><path d="M21 12.5V19a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h8" /><circle cx="8.6" cy="9.4" r="1.4" /><path d="M4 18l5-5 3.5 3.5L16 13l4 4" /><path d="M18.5 3v5.5M15.8 5.8h5.4" /></symbol>
        <symbol id="i-columns" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M12 4v16" /></symbol>
        <symbol id="i-rows" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 12h18" /></symbol>
        <symbol id="i-split" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M12 4v3M12 10.5v3M12 17v3" /></symbol>
        <symbol id="i-move-horizontal" viewBox="0 0 24 24"><path d="M6.5 8L3 12l3.5 4M17.5 8L21 12l-3.5 4M3 12h18" /></symbol>
        <symbol id="i-sparkles" viewBox="0 0 24 24"><path d="M12 4l1.8 4.2L18 10l-4.2 1.8L12 16l-1.8-4.2L6 10l4.2-1.8z" /><path d="M18 16l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8z" /></symbol>
        <symbol id="i-wand" viewBox="0 0 24 24"><path d="M4 20L15.5 8.5M13.5 6.5l4 4" /><path d="M19 3v3.4M17.3 4.7h3.4M5 4v2.4M3.8 5.2h2.4" /></symbol>

        {/* 对话与面板 */}
        <symbol id="i-server" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="7" rx="2" /><rect x="3" y="13" width="18" height="7" rx="2" /><path d="M7 7.5h.01M7 16.5h.01" /></symbol>
        <symbol id="i-shield-check" viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 4.8-3.6 7.9-8 9-4.4-1.1-8-4.2-8-9V6z" /><path d="M9 12l2.4 2.4L16 10" /></symbol>
        <symbol id="i-shield-off" viewBox="0 0 24 24"><path d="M12 3l8 3v6c0 4.8-3.6 7.9-8 9-4.4-1.1-8-4.2-8-9V6z" /><path d="M4.5 4.5l15 15" /></symbol>
        <symbol id="i-activity" viewBox="0 0 24 24"><path d="M3 12h3.6l2.6-7 4.4 14 2.6-7H21" /></symbol>
        <symbol id="i-gauge" viewBox="0 0 24 24"><path d="M4.6 18.5a9 9 0 1 1 14.8 0" /><path d="M12 14l4.2-4.2" /></symbol>
        <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4" /><path d="M12 2v2.4M12 19.6V22M2 12h2.4M19.6 12H22M5.2 5.2l1.7 1.7M17.1 17.1l1.7 1.7M18.8 5.2l-1.7 1.7M6.9 17.1l-1.7 1.7" /></symbol>
        <symbol id="i-palette" viewBox="0 0 24 24"><path d="M12 21a9 9 0 1 1 0-18c5 0 9 3.5 9 7.9 0 2.4-2 4.1-4.5 4.1H15a2 2 0 0 0-1.4 3.4A1.9 1.9 0 0 1 12 21z" /><circle cx="8" cy="10.5" r="1" /><circle cx="12" cy="7.6" r="1" /><circle cx="16" cy="10.5" r="1" /></symbol>
        <symbol id="i-spline" viewBox="0 0 24 24"><path d="M5.5 18.5C13 18.5 18.5 13 18.5 5.5" /><circle cx="20" cy="4" r="2" /><circle cx="4" cy="20" r="2" /></symbol>
        <symbol id="i-contrast" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 3v18" /></symbol>
        <symbol id="i-droplets" viewBox="0 0 24 24"><path d="M13.5 3.5s5 5.4 5 8.9a5 5 0 0 1-10 0c0-3.5 5-8.9 5-8.9z" /><path d="M6.4 13.6s2.6 2.9 2.6 4.5a2.6 2.6 0 0 1-5.2 0c0-1.6 2.6-4.5 2.6-4.5z" /></symbol>

        {/* 技能 / 插件 / 设置 */}
        <symbol id="i-shapes" viewBox="0 0 24 24"><circle cx="8.2" cy="8.2" r="4.2" /><rect x="12" y="12" width="8.5" height="8.5" rx="1.5" /></symbol>
        <symbol id="i-book" viewBox="0 0 24 24"><path d="M12 6.4v13.4" /><path d="M12 6.4C10.4 5 7.8 4.4 4 4.4v13.4c3.8 0 6.4.6 8 2 1.6-1.4 4.2-2 8-2V4.4c-3.8 0-6.4.6-8 2z" /></symbol>
        <symbol id="i-film" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M3 15h18M8 4v16M16 4v16" /></symbol>
        <symbol id="i-mountain" viewBox="0 0 24 24"><path d="M3 20l6.2-11 4.3 6.3 2.3-3.3L21 20z" /><path d="M7.6 13.4c.9-.9 1.9-.9 2.8 0" /></symbol>
        <symbol id="i-moon" viewBox="0 0 24 24"><path d="M20.5 14.2A8.6 8.6 0 0 1 9.8 3.5 8.6 8.6 0 1 0 20.5 14.2z" /></symbol>
        <symbol id="i-box" viewBox="0 0 24 24"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z" /><path d="M4 7.5l8 4.5 8-4.5M12 12v9" /></symbol>
        <symbol id="i-package-plus" viewBox="0 0 24 24"><path d="M20 11.5v-4L12 3 4 7.5v9L12 21l3.4-1.9" /><path d="M4 7.5l8 4.5 8-4.5M12 12v6" /><path d="M18 15v6M15 18h6" /></symbol>
        <symbol id="i-cpu" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="9.8" y="9.8" width="4.4" height="4.4" rx="1" /><path d="M9.5 2v4M14.5 2v4M9.5 18v4M14.5 18v4M2 9.5h4M2 14.5h4M18 9.5h4M18 14.5h4" /></symbol>
        <symbol id="i-lock" viewBox="0 0 24 24"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></symbol>
        <symbol id="i-brain" viewBox="0 0 24 24"><path d="M11 4.2A3 3 0 0 0 6 6.4v.4a3 3 0 0 0-1 5.4v1.3a3 3 0 0 0 3 3H8a2.5 2.5 0 0 0 3 2.4z" /><path d="M13 4.2A3 3 0 0 1 18 6.4v.4a3 3 0 0 1 1 5.4v1.3a3 3 0 0 1-3 3H16a2.5 2.5 0 0 1-3 2.4z" /></symbol>
        <symbol id="i-terminal" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7.5 9.5l3 2.5-3 2.5M13 15h3.5" /></symbol>
        <symbol id="i-cloud" viewBox="0 0 24 24"><path d="M7.2 18.5h9.3a4.2 4.2 0 0 0 0-8.4 5.6 5.6 0 0 0-10.7 1.6 3.4 3.4 0 0 0 1.4 6.8z" /></symbol>
      </defs>
    </svg>
  );
}

export type IconName =
  | "home" | "library" | "template" | "skill" | "plugin" | "settings"
  | "aperture" | "folder-plus" | "import" | "relocate"
  | "arrow-right" | "arrow-up" | "arrow-up-right" | "check"
  | "collapse" | "close" | "add" | "min" | "max"
  | "chevron-down" | "chevron-left" | "chevron-right" | "info" | "download" | "reset"
  | "search" | "folder" | "folder-search" | "refresh" | "trash" | "reveal" | "tag" | "drive"
  | "image" | "image-plus" | "columns" | "rows" | "split" | "move-horizontal" | "sparkles" | "wand"
  | "server" | "shield-check" | "shield-off" | "activity" | "gauge"
  | "sun" | "palette" | "spline" | "contrast" | "droplets"
  | "shapes" | "book" | "film" | "mountain" | "moon"
  | "box" | "package-plus" | "cpu" | "lock" | "brain" | "terminal" | "cloud";

type IconProps = { name: IconName; className?: string };

export function Icon({ name, className }: IconProps) {
  return (
    <svg className={className ? `icon ${className}` : "icon"} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}

type BrandLogoProps = { className?: string };

// 极简字母标：accent 实心圆 + 一笔圆角直角 L 笔画。
export function BrandLogo({ className }: BrandLogoProps) {
  return (
    <svg
      className={className ? `brand-logo ${className}` : "brand-logo"}
      viewBox="0 0 32 32"
      aria-hidden="true"
    >
      <circle cx="16" cy="16" r="16" fill="#b65d3d" />
      <path d="M12.5 9.5v13h10" fill="none" stroke="#faf7f0" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
