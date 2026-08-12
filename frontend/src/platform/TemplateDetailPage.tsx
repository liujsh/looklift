import { useEffect, useState, type CSSProperties } from "react";
import type { LookliftClient } from "../api/client";
import type { Analysis, ParamContract, TemplateCard } from "../api/types";
import { templateCategoryLabel } from "./templateCatalog";
import { ToneFingerprint } from "./ToneFingerprint";
import { TemplateParameterPanel } from "./TemplateParameterPanel";
import { Icon } from "./icons";

export type TemplateCurrentPhoto = { path: string; title: string };

type PreviewState =
  | { phase: "idle" | "loading"; beforeUrl?: undefined; afterUrl?: undefined; error?: undefined }
  | { phase: "ready"; beforeUrl: string; afterUrl: string; error?: undefined }
  | { phase: "error"; beforeUrl?: undefined; afterUrl?: undefined; error: string };

type TemplateDetailPageProps = {
  client: LookliftClient;
  contract?: ParamContract;
  template: TemplateCard;
  currentPhoto: TemplateCurrentPhoto | null;
  canApply: boolean;
  applying: boolean;
  status: string | null;
  error: string | null;
  onBack(): void;
  onApply(): void;
};

function useTemplateAnalysis(client: LookliftClient, name: string) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setAnalysis(null);
    setError(null);
    void client.getLook(name).then((value) => {
      if (active) setAnalysis(value);
    }).catch((reason: unknown) => {
      if (active) setError(reason instanceof Error ? reason.message : String(reason));
    });
    return () => { active = false; };
  }, [client, name]);
  return { analysis, error };
}

function useCurrentPhotoPreview(client: LookliftClient, analysis: Analysis | null, currentPhoto: TemplateCurrentPhoto | null): PreviewState {
  const [state, setState] = useState<PreviewState>({ phase: "idle" });
  useEffect(() => {
    if (!analysis || !currentPhoto) {
      setState({ phase: "idle" });
      return;
    }
    const controller = new AbortController();
    let active = true;
    let urls: string[] = [];
    setState({ phase: "loading" });
    void Promise.all([
      client.preview({ path: currentPhoto.path, analysis, factor: 0 }, controller.signal),
      client.preview({ path: currentPhoto.path, analysis, factor: 1 }, controller.signal),
    ]).then(([before, after]) => {
      if (!active) return;
      urls = [URL.createObjectURL(before), URL.createObjectURL(after)];
      setState({ phase: "ready", beforeUrl: urls[0], afterUrl: urls[1] });
    }).catch((reason: unknown) => {
      if (!active || (reason instanceof DOMException && reason.name === "AbortError")) return;
      setState({ phase: "error", error: reason instanceof Error ? reason.message : String(reason) });
    });
    return () => {
      active = false;
      controller.abort();
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [analysis, client, currentPhoto]);
  return state;
}

function BeforeAfter({ beforeUrl, afterUrl }: { beforeUrl: string; afterUrl: string }) {
  const [position, setPosition] = useState(50);
  return <div className="template-before-after" style={{ "--template-split": `${position}%` } as CSSProperties}>
    <img src={afterUrl} alt="模板效果" />
    <div className="template-before-layer"><img src={beforeUrl} alt="原片" /></div>
    <span className="template-ba-tag template-ba-left">原片</span><span className="template-ba-tag template-ba-right">效果</span>
    <span className="template-ba-divider"><i>↔</i></span>
    <input aria-label="调整原片与效果分割位置" type="range" min="0" max="100" value={position} onChange={(event) => setPosition(Number(event.currentTarget.value))} />
  </div>;
}

export function TemplateDetailPage(props: TemplateDetailPageProps) {
  const { client, contract, template, currentPhoto, canApply, applying, status, error, onBack, onApply } = props;
  const detail = useTemplateAnalysis(client, template.name);
  const preview = useCurrentPhotoPreview(client, detail.analysis, currentPhoto);

  return <main className="template-detail-page" aria-label={`${template.name}模板详情`}>
    <header className="template-detail-topbar">
      <button className="template-back-button template-icon-button" type="button" aria-label="返回模板目录" title="返回模板目录" onClick={onBack}><Icon name="arrow-right" /></button>
      <div><h1>{template.name}</h1><p>{templateCategoryLabel(template.category)} · {template.source === "built_in" ? "官方模板 · 只读" : "我的模板 · 可编辑"}</p></div>
      <span />
      <button className="template-detail-apply template-icon-button" type="button" aria-label={applying ? "正在应用模板" : "应用到当前照片"} title={applying ? "正在应用模板" : "应用到当前照片"} disabled={!canApply || applying || !detail.analysis} onClick={onApply}>{applying ? <span className="template-button-spinner" /> : <Icon name="check" />}</button>
    </header>

    <div className="template-detail-page-scroll">
      <section className="template-detail-intro">
        <div className="template-detail-preview">
          {preview.phase === "ready" ? <BeforeAfter beforeUrl={preview.beforeUrl} afterUrl={preview.afterUrl} /> : <div className="template-detail-fingerprint"><ToneFingerprint template={template} /></div>}
          {preview.phase === "loading" && <p className="template-preview-status">正在生成当前照片的临时预览…</p>}
          {preview.phase === "error" && <p className="template-preview-status template-preview-error">临时预览失败：{preview.error}</p>}
          <p className="template-preview-caption">{preview.phase === "ready" ? `当前照片“${currentPhoto?.title}”的引擎临时效果，拖动分割线查看对比。` : "没有可用的授权预览照片，已回退到白盒参数指纹；它不是照片效果图。"}</p>
        </div>
        <div className="template-detail-overview">
          <p className="template-detail-kicker">风格说明</p>
          <h2>{template.summary}</h2>
          <p className="template-detail-scenes"><b>适用场景</b>{template.suitable_for.join(" · ")}</p>
          <blockquote>{template.principles[0]}</blockquote>
          {template.principles.slice(1).map((item) => <p key={item}>{item}</p>)}
        </div>
      </section>

      {!canApply && <p className="template-detail-message">请先从图库或快速修图打开一张照片，再应用这个模板。</p>}
      {error && <p className="template-detail-message is-error" role="alert">{error}</p>}
      {!error && status && <p className="template-detail-message is-ok" role="status">{status}</p>}
      {detail.error && <p className="template-detail-message is-error" role="alert">完整参数载入失败：{detail.error}</p>}

      <section className="template-full-parameters">
        <div className="template-section-heading"><div><p>完整白盒参数</p><h2>这个风格具体改了什么</h2></div><span>所有数值均来自模板 analysis，可在调整面板继续修改</span></div>
        {!detail.analysis ? <div className="template-parameter-loading">正在载入完整参数…</div> : <TemplateParameterPanel analysis={detail.analysis} contract={contract} />}
      </section>

      <section className="template-detail-steps-section">
        <div className="template-section-heading"><div><p>调整步骤</p><h2>风格形成过程</h2></div></div>
        <ol className="template-steps">{template.steps.map((step) => <li key={step}>{step}</li>)}</ol>
      </section>
    </div>
  </main>;
}
