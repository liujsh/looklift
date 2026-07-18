import { useState } from "react";
import type { BasicAnalysis, EffectsAnalysis, ParamContract } from "../api/types";
import { AnalysisBrief } from "./AnalysisBrief";
import { BASIC_CONTROLS, EFFECT_CONTROLS, createNeutralAnalysis, requireRule } from "../panel/contractModel";
import { ColorGradingWheels } from "../panel/ColorGradingWheels";
import { PANEL_GROUPS } from "../panel/groups";
import { HslMixer } from "../panel/HslMixer";
import { SliderControl } from "../panel/SliderControl";
import { StrengthSlider } from "../panel/StrengthSlider";
import { ToneCurve } from "../panel/ToneCurve";
import { editorStore, useEditorState } from "../store/editorStore";

type PanelPaneProps = { contract?: ParamContract };

export function PanelPane({ contract }: PanelPaneProps) {
  const editor = useEditorState();
  const analysis = editor.displayAnalysis;
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
          onChange={(value) => editorStore.previewFragment(
            "basic", { ...analysis.basic, [field]: value },
          )}
        />;
      });
    }
    if (groupId === "hsl") return <HslMixer
      contract={contract}
      value={analysis.hsl}
      onChange={(value) => editorStore.previewFragment("hsl", value)}
    />;
    if (groupId === "tone-curve") return <ToneCurve
      value={analysis.tone_curve}
      onChange={(value) => editorStore.previewFragment("tone_curve", value)}
    />;
    if (groupId === "color-grading") return <ColorGradingWheels
      contract={contract}
      value={analysis.color_grading}
      onChange={(value) => editorStore.previewFragment("color_grading", value)}
    />;
    return EFFECT_CONTROLS.map(({ path, label }) => {
      const field = path.slice("effects.".length) as keyof EffectsAnalysis;
      return <SliderControl
        key={path}
        label={label}
        rule={requireRule(contract, path)}
        value={analysis.effects[field]}
        onChange={(value) => editorStore.previewFragment(
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
          disabled={!editor.analysis || !contract}
          onClick={() => {
            if (!contract) return;
            editorStore.setFactor(1);
            editorStore.commitAnalysis(createNeutralAnalysis(contract), "manual");
          }}
        >重置</button>
      </header>

      <StrengthSlider
        factor={editor.factor}
        disabled={!editor.analysis}
        onChange={editorStore.setFactor}
      />

      {analysis && <AnalysisBrief analysis={analysis} />}

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
                <div className="group-content">
                  {renderGroup(group.id)}
                </div>
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
