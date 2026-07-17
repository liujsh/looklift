import { useState } from "react";
import type { BasicAnalysis, EffectsAnalysis, ParamContract } from "../api/types";
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
  const [openGroup, setOpenGroup] = useState<string>(PANEL_GROUPS[0].id);

  const renderGroup = (groupId: string) => {
    if (!editor.analysis || !contract) return "载入分析结果后显示参数";
    if (groupId === "basic") {
      return BASIC_CONTROLS.map(({ path, label }) => {
        const field = path.slice("basic.".length) as keyof BasicAnalysis;
        return <SliderControl
          key={path}
          label={label}
          rule={requireRule(contract, path)}
          value={editor.analysis!.basic[field]}
          onChange={(value) => editorStore.updateFragment(
            "basic", { ...editor.analysis!.basic, [field]: value }, "manual",
          )}
        />;
      });
    }
    if (groupId === "hsl") return <HslMixer
      contract={contract}
      value={editor.analysis.hsl}
      onChange={(value) => editorStore.updateFragment("hsl", value, "manual")}
    />;
    if (groupId === "tone-curve") return <ToneCurve
      value={editor.analysis.tone_curve}
      onChange={(value) => editorStore.updateFragment("tone_curve", value, "manual")}
    />;
    if (groupId === "color-grading") return <ColorGradingWheels
      contract={contract}
      value={editor.analysis.color_grading}
      onChange={(value) => editorStore.updateFragment("color_grading", value, "manual")}
    />;
    return EFFECT_CONTROLS.map(({ path, label }) => {
      const field = path.slice("effects.".length) as keyof EffectsAnalysis;
      return <SliderControl
        key={path}
        label={label}
        rule={requireRule(contract, path)}
        value={editor.analysis!.effects[field]}
        onChange={(value) => editorStore.updateFragment(
          "effects", { ...editor.analysis!.effects, [field]: value }, "manual",
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
          onClick={() => contract && editorStore.commitAnalysis(createNeutralAnalysis(contract), "manual")}
        >重置</button>
      </header>

      <StrengthSlider
        factor={editor.factor}
        disabled={!editor.analysis}
        onChange={editorStore.setFactor}
      />

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
