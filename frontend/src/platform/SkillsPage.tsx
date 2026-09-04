import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { LookSummary } from "../api/types";
import { Icon, type IconName } from "./icons";

type InstalledSkill = {
  id: string;
  name: string;
  source: string;
  description: string;
  version: string;
  inputs: string;
  outputs: string;
  example: string;
  limits: string;
  icon: IconName;
  user?: boolean;
};

const BUILTIN_SKILLS: InstalledSkill[] = [
  { id: "abstract-collage", icon: "shapes", name: "抽象风格拼接", source: "LookLift 内置", description: "从照片提取色彩与形状，生成可编辑的抽象拼接参考。", version: "1.0", inputs: "照片", outputs: "白盒调色参数、拼接参考", example: "把这张照片做成克制的抽象拼接", limits: "不重绘原照片，不输出像素生图" },
  { id: "zine-layout", icon: "book", name: "Zine / 小志排版", source: "LookLift 内置", description: "将一组照片整理为有节奏的小志叙事与版式建议。", version: "1.0", inputs: "照片或图库选集", outputs: "版式建议、调色参数", example: "做成一本黑白旅行小志", limits: "需要用户确认照片顺序与最终导出" },
  { id: "film-look", icon: "film", name: "胶片质感", source: "LookLift 内置", description: "以白盒参数模拟常见胶片的色彩、颗粒与对比关系。", version: "1.0", inputs: "照片", outputs: "白盒调色参数", example: "增加温暖的 35mm 胶片质感", limits: "不绑定具体胶片品牌或扫描器" },
];

// 用户保存的技能按名称哈希取一个稳定图标。
const USER_ICONS: readonly IconName[] = ["mountain", "moon", "sun", "droplets", "palette"];

function userIcon(name: string): IconName {
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
  return USER_ICONS[hash % USER_ICONS.length];
}

export function SkillsPage({ client }: { client: LookliftClient }) {
  const [looks, setLooks] = useState<LookSummary[]>([]);
  useEffect(() => { void client.listLooks().then(setLooks).catch(() => undefined); }, [client]);
  const skills: InstalledSkill[] = [
    ...BUILTIN_SKILLS,
    ...looks.filter((look) => look.source === "user").map((look) => ({
      id: `look:${look.name}`,
      icon: userIcon(look.name),
      name: look.name,
      source: "用户保存",
      description: look.summary || "用户保存的白盒调色技能。",
      version: "本地",
      inputs: "照片",
      outputs: "白盒调色参数",
      example: `将照片应用“${look.name}”`,
      limits: "仅修改参数契约允许的字段",
      user: true,
    })),
  ];

  return (
    <main className="skills-page" aria-label="技能">
      <header>
        <div>
          <p className="pane-kicker">Installed Skills</p>
          <h1>技能</h1>
        </div>
        <p>这里只展示已安装的图像处理技能。使用时请在 Studio 输入框的「＋」中选择。</p>
      </header>

      <section className="skills-grid" aria-label="已安装技能">
        {skills.map((skill) => (
          <article className="skill-card" key={skill.id} data-source={skill.user ? "user" : "builtin"}>
            <header>
              <div>
                <span className="skill-mark" aria-hidden="true"><Icon name={skill.icon} /></span>
                <div>
                  <h2>{skill.name}</h2>
                  <p>{skill.source} · v{skill.version}</p>
                </div>
              </div>
              <span className="skill-badge">{skill.user ? "用户保存" : "已安装"}</span>
            </header>
            <p>{skill.description}</p>
            <dl>
              <div><dt>输入</dt><dd>{skill.inputs}</dd></div>
              <div><dt>输出</dt><dd>{skill.outputs}</dd></div>
              <div><dt>示例</dt><dd>{skill.example}</dd></div>
              <div><dt>能力限制</dt><dd>{skill.limits}</dd></div>
            </dl>
          </article>
        ))}
      </section>
    </main>
  );
}
