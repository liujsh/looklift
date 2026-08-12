import { useMemo, useState, type CSSProperties } from "react";
import type { Analysis, ParamContract, ParamRule } from "../api/types";
import { BASIC_CONTROLS, EFFECT_CONTROLS, GRADING_ZONES, HSL_COLORS } from "../panel/contractModel";
import { sampleMonotoneCurve } from "../panel/toneCurveModel";
import { formatTemplateParameter } from "./templateAnalysis";

type TemplateParameterPanelProps = { analysis: Analysis; contract?: ParamContract };
type HslField = "hue" | "saturation" | "luminance";

const HSL_FIELDS: ReadonlyArray<[HslField, string]> = [
  ["hue", "色相"], ["saturation", "饱和度"], ["luminance", "明亮度"],
];

function changed(value: number, rule?: ParamRule): boolean {
  return Math.abs(value - (rule?.default ?? 0)) > 0.0001;
}

function ReadOnlySlider(props: { label: string; value: number; rule?: ParamRule; tone?: string }) {
  const { label, value, rule, tone } = props;
  const span = rule ? rule.max - rule.min : 0;
  const valuePercent = span > 0 ? (value - rule!.min) / span * 100 : 50;
  const originPercent = span > 0 ? (rule!.default - rule!.min) / span * 100 : 50;
  const start = Math.min(valuePercent, originPercent);
  const width = Math.abs(valuePercent - originPercent);
  const style = {
    "--slider-value": `${Math.max(0, Math.min(100, valuePercent))}%`,
    "--slider-origin": `${Math.max(0, Math.min(100, originPercent))}%`,
    "--slider-start": `${Math.max(0, Math.min(100, start))}%`,
    "--slider-width": `${Math.max(0, Math.min(100, width))}%`,
  } as CSSProperties;
  return <div className="template-visual-slider" data-tone={tone} data-has-rule={Boolean(rule)}>
    <div className="template-visual-slider-head"><span>{label}</span><output>{formatTemplateParameter(value)}</output></div>
    <div className="template-visual-slider-track" style={style} aria-label={`${label} ${value}`}>
      <i className="template-slider-origin" /><i className="template-slider-fill" /><i className="template-slider-thumb" />
    </div>
  </div>;
}

function ToneCurvePreview({ analysis }: { analysis: Analysis }) {
  const samples = sampleMonotoneCurve(analysis.tone_curve, 64);
  const path = samples.map((point, index) => `${index ? "L" : "M"}${point.input},${255 - point.output}`).join(" ");
  return <div className="template-curve-preview">
    <svg viewBox="0 0 255 255" role="img" aria-label="模板色调曲线">
      <path className="curve-grid" d="M0 63.75H255 M0 127.5H255 M0 191.25H255 M63.75 0V255 M127.5 0V255 M191.25 0V255" />
      <path className="curve-diagonal" d="M0 255L255 0" />
      <path className="curve-line" d={path} />
      {analysis.tone_curve.map((point, index) => <circle key={`${index}-${point.input}`} cx={point.input} cy={255 - point.output} r="4" />)}
    </svg>
    <p>横轴为输入亮度，纵轴为输出亮度；曲线偏离对角线的部分就是模板对明暗关系的塑造。</p>
  </div>;
}

function GradingWheel(props: { label: string; hue: number; saturation: number; luminance: number }) {
  const radians = (props.hue - 90) * Math.PI / 180;
  const radius = Math.min(36, Math.max(0, props.saturation) / 100 * 36);
  const style = {
    "--wheel-x": `${50 + Math.cos(radians) * radius}%`,
    "--wheel-y": `${50 + Math.sin(radians) * radius}%`,
    "--wheel-color": `hsl(${props.hue} ${Math.max(0, props.saturation)}% 50%)`,
  } as CSSProperties;
  return <article className="template-grading-wheel">
    <h4>{props.label}</h4>
    <div className="template-color-wheel" style={style}><i /></div>
    <dl><div><dt>色相</dt><dd>{Math.round(props.hue)}°</dd></div><div><dt>饱和度</dt><dd>{formatTemplateParameter(props.saturation)}</dd></div><div><dt>明亮度</dt><dd>{formatTemplateParameter(props.luminance)}</dd></div></dl>
  </article>;
}

export function TemplateParameterPanel({ analysis, contract }: TemplateParameterPanelProps) {
  const [showAll, setShowAll] = useState(false);
  const [hslField, setHslField] = useState<HslField>("hue");
  const basic = BASIC_CONTROLS.filter(({ path }) => {
    const key = path.slice("basic.".length) as keyof Analysis["basic"];
    return showAll || changed(analysis.basic[key], contract?.[path]);
  });
  const effects = EFFECT_CONTROLS.filter(({ path }) => {
    const key = path.slice("effects.".length) as keyof Analysis["effects"];
    return showAll || changed(analysis.effects[key], contract?.[path]);
  });
  const hslEntries = analysis.hsl.filter((entry) => showAll || HSL_FIELDS.some(([field]) => changed(entry[field], contract?.[`hsl.${entry.color}.${field}`])));
  const gradingZones = GRADING_ZONES.filter(([contractZone]) => {
    const zone = contractZone === "global" ? "global_" : contractZone;
    const value = analysis.color_grading[zone];
    return showAll || changed(value.hue, contract?.[`color_grading.${contractZone}.hue`]) || changed(value.saturation, contract?.[`color_grading.${contractZone}.saturation`]) || changed(value.luminance, contract?.[`color_grading.${contractZone}.luminance`]);
  });
  const curveChanged = analysis.tone_curve.some((point) => Math.abs(point.input - point.output) > .0001);
  const gradingControlsChanged = changed(analysis.color_grading.blending, contract?.["color_grading.blending"]) || changed(analysis.color_grading.balance, contract?.["color_grading.balance"]);
  const changedCount = useMemo(() => basic.length + effects.length + hslEntries.length + gradingZones.length + (curveChanged ? 1 : 0) + (gradingControlsChanged ? 1 : 0), [basic.length, curveChanged, effects.length, gradingControlsChanged, gradingZones.length, hslEntries.length]);

  return <section className="template-parameter-panel">
    <div className="template-parameter-mode">
      <div><strong>参数拆解</strong><span>{showAll ? "显示模板中的全部白盒参数" : `显示 ${changedCount} 组有调整的参数`}</span></div>
      <div className="template-mode-switch" role="group" aria-label="参数显示范围">
        <button type="button" aria-pressed={!showAll} onClick={() => setShowAll(false)}>仅看有调整</button>
        <button type="button" aria-pressed={showAll} onClick={() => setShowAll(true)}>显示全部</button>
      </div>
    </div>

    {basic.length > 0 && <section className="template-control-section">
      <header><div><span>01</span><h3>基础调整</h3></div><p>先决定整体明暗、反差与通透感。</p></header>
      <div className="template-slider-columns">{basic.map(({ path, label }) => {
        const key = path.slice("basic.".length) as keyof Analysis["basic"];
        return <ReadOnlySlider key={path} label={label} value={analysis.basic[key]} rule={contract?.[path]} tone={key === "temperature_shift" ? "temperature" : key === "tint_shift" ? "tint" : undefined} />;
      })}</div>
    </section>}

    {(showAll || curveChanged) && <section className="template-control-section">
      <header><div><span>02</span><h3>色调曲线</h3></div><p>直接观察黑场、白场和中间调如何被重塑。</p></header>
      <ToneCurvePreview analysis={analysis} />
    </section>}

    {hslEntries.length > 0 && <section className="template-control-section">
      <header><div><span>03</span><h3>HSL 颜色</h3></div><p>逐种颜色查看色相、饱和度与明亮度。</p></header>
      <div className="template-hsl-tabs" role="tablist" aria-label="HSL 参数维度">{HSL_FIELDS.map(([field, label]) => <button type="button" role="tab" aria-selected={hslField === field} key={field} onClick={() => setHslField(field)}>{label}</button>)}</div>
      <div className="template-hsl-list">{hslEntries.map((entry) => {
        const label = HSL_COLORS.find(([color]) => color === entry.color)?.[1] ?? entry.color;
        return <div className="template-hsl-row" data-color={entry.color} key={entry.color}><i /><ReadOnlySlider label={label} value={entry[hslField]} rule={contract?.[`hsl.${entry.color}.${hslField}`]} tone={`hsl-${entry.color}`} /></div>;
      })}</div>
    </section>}

    {(gradingZones.length > 0 || showAll || gradingControlsChanged) && <section className="template-control-section">
      <header><div><span>04</span><h3>颜色分级</h3></div><p>用色轮理解阴影、亮部和中间调的冷暖倾向。</p></header>
      <div className="template-grading-grid">{gradingZones.map(([contractZone, label]) => {
        const zone = contractZone === "global" ? "global_" : contractZone;
        return <GradingWheel key={zone} label={label} {...analysis.color_grading[zone]} />;
      })}</div>
      {(showAll || gradingControlsChanged) && <div className="template-slider-columns is-compact">
        <ReadOnlySlider label="混合" value={analysis.color_grading.blending} rule={contract?.["color_grading.blending"]} />
        <ReadOnlySlider label="平衡" value={analysis.color_grading.balance} rule={contract?.["color_grading.balance"]} />
      </div>}
    </section>}

    {effects.length > 0 && <section className="template-control-section">
      <header><div><span>05</span><h3>效果</h3></div><p>最后加入暗角和颗粒，控制画面收束与质感。</p></header>
      <div className="template-slider-columns is-compact">{effects.map(({ path, label }) => {
        const key = path.slice("effects.".length) as keyof Analysis["effects"];
        return <ReadOnlySlider key={path} label={label} value={analysis.effects[key]} rule={contract?.[path]} />;
      })}</div>
    </section>}
  </section>;
}
