import type { TemplateCard } from "../api/types";
import { templateCategoryLabel } from "./templateCatalog";
import { ToneFingerprint } from "./ToneFingerprint";
import { Icon } from "./icons";

type TemplateContactCardProps = {
  template: TemplateCard;
  selected: boolean;
  onSelect(): void;
};

export function TemplateContactCard({ template, selected, onSelect }: TemplateContactCardProps) {
  return (
    <button
      className="template-contact-card"
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="template-card-media">
        <ToneFingerprint template={template} compact />
        <span className="template-preview-note">无预览 · 参数指纹</span>
      </span>
      <span className="template-card-copy">
        <strong>{template.name}</strong>
        <span className="template-card-meta"><b>{templateCategoryLabel(template.category)}</b></span>
        <span className="template-card-summary">{template.summary || "已保存的白盒参数组合"}</span>
        <span className="template-card-foot">
          <span>{template.key_parameters.length} 项参数 · 强度 100%</span>
          <span className="template-card-cta"><Icon name="wand" />查看参数</span>
        </span>
      </span>
    </button>
  );
}
