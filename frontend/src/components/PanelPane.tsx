import { useState } from "react";
import type { BasicAnalysis, EffectsAnalysis, ImageInfo, ParamContract } from "../api/types";
import type { HistogramState } from "../features/histogram/histogramController";
import { AnalysisBrief } from "./AnalysisBrief";
import { BASIC_CONTROLS, EFFECT_CONTROLS, createNeutralAnalysis, requireRule } from "../panel/contractModel";
import { ColorGradingWheels } from "../panel/ColorGradingWheels";
import { PANEL_GROUPS } from "../panel/groups";
import { HslMixer } from "../panel/HslMixer";
import { SliderControl } from "../panel/SliderControl";
import { StrengthSlider } from "../panel/StrengthSlider";
import { ToneCurve } from "../panel/ToneCurve";
import { editorStore, useEditorState } from "../store/editorStore";
import { HistogramPanel } from "./HistogramPanel";

type PanelPaneProps = {
  contract?: ParamContract;
  onFormalAnalysis?(analysis: ReturnType<typeof createNeutralAnalysis>, source: "manual"): void;
  histogram?: HistogramState;
  imageInfo?: ImageInfo | null;
};

const EMPTY_HISTOGRAM: HistogramState = Object.freeze({
  status: "idle", data: null, signature: null, error: null,
});

export function PanelPane({ contract, onFormalAnalysis, histogram = EMPTY_HISTOGRAM, imageInfo = null }: PanelPaneProps) {
  const editor = useEditorState();
  const analysis = editor.displayAnalysis;
  const pending = editor.pendingPreview !== null;
  const locked = pending || editor.activeAiRequestId !== null;
  const [openGroup, setOpenGroup] = useState<string>(PANEL_GROUPS[0].id);

  const renderGroup = (groupId: string) => {
    if (!analysis || !contract) return "载入分析结果后显示参数";
    if (groupId === "basic") {
      return BASIC_CONTROLS.map(({ path, label }) => {
        const field = path.slice("basic.".length) as keyof BasicAnalysis;
        return <SliderControl
          key={path}
          label={label}
          rule={requireRule(contract, path)}
          value={analysis.basic[field]}
          disabled={locked}
          onChange={(value) => !locked && editorStore.previewFragment(
            "basic", { ...analysis.basic, [field]: value },
          )}
        />;
      });
    }
    if (groupId === "hsl") return <HslMixer
      contract={contract}
      value={analysis.hsl}
      onChange={(value) => !locked && editorStore.previewFragment("hsl", value)}
    />;
    if (groupId === "tone-curve") return <ToneCurve
      value={analysis.tone_curve}
      onChange={(value) => !locked && editorStore.previewFragment("tone_curve", value)}
    />;
    if (groupId === "color-grading") return <ColorGradingWheels
      contract={contract}
      value={analysis.color_grading}
      onChange={(value) => !locked && editorStore.previewFragment("color_grading", value)}
    />;
    return EFFECT_CONTROLS.map(({ path, label }) => {
      const field = path.slice("effects.".length) as keyof EffectsAnalysis;
      return <SliderControl
        key={path}
        label={label}
        rule={requireRule(contract, path)}
        value={analysis.effects[field]}
        disabled={locked}
        onChange={(value) => !locked && editorStore.previewFragment(
          "effects", { ...analysis.effects, [field]: value },
        )}
      />;
    });
  };

  return (
    <aside className="panel-pane" data-pane="controls" aria-label="调整面板">
      <header className="pane-heading">
        <div>
          <p className="pane-kicker">编辑</p>
          <h2>调整</h2>
        </div>
        <button
          type="button"
          disabled={!editor.analysis || !contract || locked}
          onClick={() => {
            if (!contract) return;
            editorStore.setFactor(1);
            const neutral = createNeutralAnalysis(contract);
            editorStore.commitAnalysis(neutral, "manual");
            onFormalAnalysis?.(neutral, "manual");
          }}
        >重置</button>
      </header>

      <HistogramPanel histogram={histogram} imageInfo={imageInfo} />

      <StrengthSlider
        factor={editor.factor}
        disabled={!editor.analysis || locked}
        onChange={editorStore.setFactor}
      />

      {analysis && <AnalysisBrief analysis={analysis} />}
      {pending && <p className="panel-pending-note">当前显示 AI 候选；要修改参数，请先在左侧选择“继续手调”。</p>}
      {editor.activeAiRequestId !== null && <p className="panel-pending-note">AI 正在分析当前效果；停止或完成后可继续调整。</p>}

      <nav className="panel-groups" aria-label="调整分组">
        {PANEL_GROUPS.map((group) => {
          const expanded = openGroup === group.id;
          return (
            <div className="panel-group" data-section={group.section} key={group.id}>
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpenGroup(expanded ? "" : group.id)}
              >
                <span>{group.label}</span>
                <span aria-hidden="true">{expanded ? "−" : "+"}</span>
              </button>
              {expanded && (
                <fieldset className="group-content" disabled={locked}>
                  {renderGroup(group.id)}
                </fieldset>
              )}
            </div>
          );
        })}
      </nav>

      <div className="panel-note">
        {editor.imagePath
          ? editor.analysis ? "所有调整共享当前 analysis" : "等待分析结果回填参数"
          : "导入照片后显示参数控件"}
      </div>
    </aside>
  );
}
