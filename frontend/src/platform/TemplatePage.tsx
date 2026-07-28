import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { TemplateCard } from "../api/types";

type TemplatePageProps = {
  client: LookliftClient;
  canApply: boolean;
  onApply(name: string): Promise<void> | void;
};

const PARAMETER_LABELS: Record<string, string> = {
  temperature_shift: "色温", exposure: "曝光", contrast: "对比度", highlights: "高光",
  shadows: "阴影", whites: "白色色阶", blacks: "黑色色阶", vibrance: "自然饱和度",
  saturation: "饱和度", hue: "色相", vignette_amount: "暗角", grain_amount: "颗粒",
};

export function templateParameterLabel(path: string): string {
  const parts = path.split(".");
  const leaf = parts[parts.length - 1] ?? path;
  const section = parts.length > 2 ? `${parts[parts.length - 2]} · ` : "";
  return `${section}${PARAMETER_LABELS[leaf] ?? leaf}`;
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

export function TemplatePage({ client, canApply, onApply }: TemplatePageProps) {
  const [source, setSource] = useState<"built_in" | "user">("built_in");
  const [templates, setTemplates] = useState<readonly TemplateCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void client.listTemplates()
      .then((items) => { if (!cancelled) setTemplates(items); })
      .catch((reason) => { if (!cancelled) setError(`模板载入失败：${reason instanceof Error ? reason.message : String(reason)}`); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [client]);

  const visible = templates.filter((template) => template.source === source);
  const apply = async (template: TemplateCard) => {
    setApplying(template.name);
    setError(null);
    try {
      await onApply(template.name);
      setStatus(`已在 Studio 套用：${template.name}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setApplying(null);
    }
  };

  return (
    <main className="template-page" aria-label="大师模板">
      <header className="template-page-heading">
        <div><p className="pane-kicker">WHITE-BOX LOOKS</p><h1>大师模板</h1></div>
        <p>从原创通用风格起步，展开参数理解每一步，再按照片继续微调。</p>
        <nav className="template-source-tabs" aria-label="模板来源">
          <button type="button" aria-pressed={source === "built_in"} onClick={() => setSource("built_in")}>官方模板</button>
          <button type="button" aria-pressed={source === "user"} onClick={() => setSource("user")}>我的模板</button>
        </nav>
      </header>
      {!canApply && <p className="template-page-hint" role="status">请先从图库或快速修图打开一张照片，再直接套用模板。</p>}
      <div className="template-page-toolbar"><span>{source === "built_in" ? "原创风格课" : "你的参数收藏"}</span><strong>{loading ? "载入中" : `${templates.filter((template) => template.source === source).length} 个模板`}</strong></div>
      <section className="template-grid" aria-label={source === "built_in" ? "官方模板" : "我的模板"}>
        {visible.map((template, index) => <article className="template-card" data-source={template.source} key={template.name}>
          <div className={`template-palette template-palette-${index % 3}`} aria-hidden="true"><span /><span /></div>
          <div className="template-card-body">
            <div className="template-card-meta"><p className="template-source">{template.source === "built_in" ? "LOOKLIFT 官方" : "我的收藏"}</p><span>{template.readonly ? "只读" : "可编辑"}</span></div>
            <h2>{template.name}</h2>
            <p>{template.summary}</p>
            <div className="template-scenarios">{template.suitable_for.map((item) => <span key={item}>{item}</span>)}</div>
            <details>
              <summary>查看白盒参数课</summary>
              {template.principles.map((item) => <p key={item}>{item}</p>)}
              {template.key_parameters.length > 0 && <dl>{template.key_parameters.map((item) => <div key={item.path}>
                <dt>{templateParameterLabel(item.path)}</dt><dd>{signed(item.value)}</dd>
              </div>)}</dl>}
              {template.steps.length > 0 && <ol>{template.steps.map((step) => <li key={step}>{step}</li>)}</ol>}
            </details>
            <button className="template-apply" type="button" disabled={!canApply || applying !== null} onClick={() => void apply(template)}>
              {applying === template.name ? "正在套用…" : "直接套用到 Studio"}
            </button>
          </div>
        </article>)}
        {!loading && visible.length === 0 && <p className="template-empty">{source === "user" ? "还没有用户模板；可在 Studio 收藏当前参数。" : "暂无官方模板"}</p>}
      </section>
      {loading && <p className="template-page-status">正在载入模板…</p>}
      {error ? <p className="template-page-status template-page-error" role="alert">{error}</p> : status && <p className="template-page-status">{status}</p>}
    </main>
  );
}
