import { useEffect, useMemo, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { ParamContract, TemplateCard } from "../api/types";
import { countTemplates, filterTemplates, type TemplateCategoryFilter, visibleTemplateCategories } from "./templateCatalog";
import { TemplateContactCard } from "./TemplateContactCard";
import { TemplateDetailPage, type TemplateCurrentPhoto } from "./TemplateDetailPage";
import { Icon } from "./icons";
import "./template-page.css";

export { templateParameterLabel } from "./templateCatalog";

type TemplatePageProps = {
  client: LookliftClient;
  contract?: ParamContract;
  canApply: boolean;
  currentPhoto?: TemplateCurrentPhoto | null;
  onApply(name: string): Promise<void> | void;
};

export function TemplatePage({ client, contract, canApply, currentPhoto = null, onApply }: TemplatePageProps) {
  const [source, setSource] = useState<TemplateCard["source"]>("built_in");
  const [category, setCategory] = useState<TemplateCategoryFilter>("all");
  const [query, setQuery] = useState("");
  const [templates, setTemplates] = useState<readonly TemplateCard[]>([]);
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    void client.listTemplates()
      .then((items) => { if (!cancelled) setTemplates(items); })
      .catch((reason) => { if (!cancelled) setLoadError(`模板载入失败：${reason instanceof Error ? reason.message : String(reason)}`); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [client]);

  const visible = useMemo(
    () => filterTemplates(templates, { source, category, query }),
    [category, query, source, templates],
  );
  const categories = useMemo(() => visibleTemplateCategories(templates, source), [source, templates]);

  const selected = templates.find((item) => item.name === selectedName) ?? null;
  const chooseSource = (next: TemplateCard["source"]) => {
    setSource(next);
    setCategory("all");
    setStatus(null);
    setActionError(null);
  };
  const chooseTemplate = (template: TemplateCard) => {
    setSelectedName(template.name);
    setStatus(null);
    setActionError(null);
  };
  const applySelected = async () => {
    if (!selected || applying) return;
    setApplying(true);
    setStatus(null);
    setActionError(null);
    try {
      await onApply(selected.name);
      setStatus(`已应用到当前照片：${selected.name}`);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setApplying(false);
    }
  };

  if (selected) {
    return <TemplateDetailPage
      client={client}
      contract={contract}
      template={selected}
      currentPhoto={currentPhoto}
      canApply={canApply}
      applying={applying}
      status={status}
      error={actionError}
      onBack={() => setSelectedName(null)}
      onApply={() => void applySelected()}
    />;
  }

  return (
    <main className="template-library-page" aria-label="大师模板">
      <section className="template-browse-pane">
        <header className="template-browse-header">
          <div className="template-title-line">
            <div>
              <p className="pane-kicker">Master Looks</p>
              <h1>大师模板</h1>
              <p>浏览预设、看懂参数，再应用到当前照片。</p>
            </div>
            <small className={currentPhoto ? "is-on" : ""}><i />{currentPhoto ? `当前照片：${currentPhoto.title}` : "未打开照片"}</small>
          </div>

          <div className="template-filter-line">
            <nav className="template-source-switch" aria-label="模板来源">
              <button type="button" data-source="built_in" aria-pressed={source === "built_in"} onClick={() => chooseSource("built_in")}>官方模板</button>
              <button type="button" data-source="user" aria-pressed={source === "user"} onClick={() => chooseSource("user")}>我的模板</button>
            </nav>
            <label className="template-search">
              <span aria-hidden="true"><Icon name="search" /></span>
              <input aria-label="搜索模板" type="search" value={query} onChange={(event) => setQuery(event.currentTarget.value)} placeholder="搜索名称、摘要、分类或场景" />
              {query && <button type="button" aria-label="清除搜索" onClick={() => setQuery("")}><Icon name="close" /></button>}
            </label>
            <strong>{loading ? "载入中" : query ? `命中 ${visible.length} 个` : `${visible.length} 个模板`}</strong>
          </div>

          <nav className="template-category-nav" aria-label="模板分类">
            {categories.map((item) => <button type="button" key={item.id} data-category={item.id} aria-pressed={category === item.id} onClick={() => setCategory(item.id)}>{item.label}<span>{countTemplates(templates, source, item.id)}</span></button>)}
          </nav>
        </header>

        <div className="template-catalog-scroll">
          {loading ? <div className="template-catalog-grid" aria-label="正在载入模板">{Array.from({ length: 4 }, (_, index) => <div className="template-card-skeleton" key={index} />)}</div>
            : loadError ? <div className="template-catalog-message" role="alert"><h2>模板载入失败</h2><p>{loadError}</p></div>
            : visible.length > 0 ? <section className="template-catalog-grid" aria-label="模板列表">{visible.map((template) => <TemplateContactCard key={template.name} template={template} selected={false} onSelect={() => chooseTemplate(template)} />)}</section>
            : <div className="template-catalog-message"><h2>{query ? "没有匹配的模板" : "这个分类还是空的"}</h2><p>{query ? `“${query}”在当前来源与分类下没有命中。` : source === "user" ? "在修图页保存喜欢的效果后，它会带着完整白盒参数出现在这里。" : "该分类下暂时没有官方模板。"}</p>{query && <button type="button" onClick={() => setQuery("")}>清除搜索</button>}</div>}
        </div>
      </section>
    </main>
  );
}
