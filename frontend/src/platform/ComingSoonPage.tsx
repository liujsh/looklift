import type { PlatformPage } from "./platformStore";

const CONTENT: Record<PlatformPage, { title: string; version: string; description: string }> = {
  library: { title: "我的图库", version: "v2.3-A", description: "索引本机文件夹并提供缩略图、标签和版本记录；只索引，不复制原文件。" },
  import: { title: "从设备导入", version: "v2.3-B", description: "在 RAW 可行性门之后接入设备发现、选择、复制校验和重复检测。" },
  templates: { title: "大师模板", version: "v2.4", description: "提供官方与用户模板卡片、直接套用和白盒参数教学。" },
  automation: { title: "自动化技能", version: "v2.5", description: "提供显式、可预览、可恢复的批量修图工作流。" },
  plugins: { title: "插件", version: "v2.6", description: "通过受控权限扩展模型、导入、导出和元数据能力。" },
  settings: { title: "设置与帮助", version: "后续版本", description: "平台级设置、帮助和能力管理将在对应功能具备真实入口后接入。" },
};

export function ComingSoonPage({ page }: { page: PlatformPage }) {
  const content = CONTENT[page];
  return (
    <main className="coming-soon-page" aria-label={content.title}>
      <p className="pane-kicker">ROADMAP</p>
      <h1>{content.title}</h1>
      <strong>将在 {content.version} 提供</strong>
      <p>{content.description}</p>
      <span>当前版本不会使用示例数据伪装该能力已经完成。</span>
    </main>
  );
}
