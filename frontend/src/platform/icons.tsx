// 线性图标集：symbol 定义逐字对齐 docs/design/home-refresh-prototype.html 的原型 sprite。
export function IconSprite() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
      <defs>
        <symbol id="i-home" viewBox="0 0 24 24"><path d="M3 11l9-7 9 7" /><path d="M5 9.5V20h14V9.5" /><path d="M10 20v-5h4v5" /></symbol>
        <symbol id="i-library" viewBox="0 0 24 24"><rect x="7" y="4" width="13" height="13" rx="2" /><path d="M4 8v11a1 1 0 0 0 1 1h11" /><circle cx="11.5" cy="8.2" r="1.2" /><path d="M8 14.5l2.6-2.6 2 2 3-3.4 2.4 2.6" /></symbol>
        <symbol id="i-template" viewBox="0 0 24 24"><path d="M12 3l8 4.5-8 4.5-8-4.5z" /><path d="M4 12l8 4.5 8-4.5" /><path d="M4 16.3l8 4.5 8-4.5" /></symbol>
        <symbol id="i-skill" viewBox="0 0 24 24"><path d="M13 3L5 13.5h5l-1 7.5L18 10h-5z" /></symbol>
        <symbol id="i-plugin" viewBox="0 0 24 24"><path d="M10 4a1.6 1.6 0 0 1 3.1 0c0 .9.6 1.1 1.2 1.1H16a1 1 0 0 1 1 1v1.7c0 .6.2 1.2 1.1 1.2a1.6 1.6 0 0 1 0 3.1c-.9 0-1.1.6-1.1 1.2V16a1 1 0 0 1-1 1h-1.7c-.6 0-1.2.2-1.2 1.1a1.6 1.6 0 0 1-3.1 0c0-.9-.6-1.1-1.2-1.1H6a1 1 0 0 1-1-1v-1.8c0-.6-.2-1.2-1.1-1.2a1.6 1.6 0 0 1 0-3.1c.9 0 1.1-.6 1.1-1.2V6a1 1 0 0 1 1-1h1.8c.6 0 1.2-.2 1.2-1.1z" /></symbol>
        <symbol id="i-settings" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V15z" /></symbol>
        <symbol id="i-aperture" viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 3l4.6 8M21 12h-9.2M16.6 16.9L12 9M12 21l-4.6-8M3 12h9.2M7.4 7.1L12 15" /></symbol>
        <symbol id="i-folder-plus" viewBox="0 0 24 24"><path d="M4 7a1 1 0 0 1 1-1h3.6l2 2H19a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z" /><path d="M12 11.5v5M9.5 14h5" /></symbol>
        <symbol id="i-import" viewBox="0 0 24 24"><path d="M12 3v10.5" /><path d="M8 9.5l4 4 4-4" /><path d="M4 15v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" /></symbol>
        <symbol id="i-relocate" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" /><path d="M12 2.5v3.5M12 18v3.5M2.5 12h3.5M18 12h3.5" /></symbol>
        <symbol id="i-arrow-right" viewBox="0 0 24 24"><path d="M5 12h13M13 6l6 6-6 6" /></symbol>
        <symbol id="i-collapse" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M10 4v16" /><path d="M16.5 9.5L14 12l2.5 2.5" /></symbol>
        <symbol id="i-close" viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18" /></symbol>
        <symbol id="i-add" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14" /></symbol>
        <symbol id="i-min" viewBox="0 0 24 24"><path d="M5 12h14" /></symbol>
        <symbol id="i-max" viewBox="0 0 24 24"><rect x="5" y="5" width="14" height="14" rx="1" /></symbol>
      </defs>
    </svg>
  );
}

export type IconName =
  | "home" | "library" | "template" | "skill" | "plugin" | "settings"
  | "aperture" | "folder-plus" | "import" | "relocate" | "arrow-right"
  | "collapse" | "close" | "add" | "min" | "max";

type IconProps = { name: IconName; className?: string };

export function Icon({ name, className }: IconProps) {
  return (
    <svg className={className ? `icon ${className}` : "icon"} aria-hidden="true">
      <use href={`#i-${name}`} />
    </svg>
  );
}

type BrandLogoProps = { className?: string };

// A1「连续上扬 L」logo：深底圆角方块 + 白色 L 曲线 + #c96847 末端上扬。
export function BrandLogo({ className }: BrandLogoProps) {
  return (
    <svg
      className={className ? `brand-logo ${className}` : "brand-logo"}
      viewBox="0 0 128 128"
      aria-label="LookLift"
    >
      <rect width="128" height="128" rx="29" fill="#211e1a" />
      <path
        d="M38 27v56c0 13 7 20 20 20h8c16 0 24-9 29-21 4-10 8-17 16-21"
        fill="none"
        stroke="#f2eee5"
        strokeWidth="12"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M92 83c5-11 10-18 19-22" fill="none" stroke="#c96847" strokeWidth="12" strokeLinecap="round" />
    </svg>
  );
}
