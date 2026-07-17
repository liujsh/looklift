import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { ColorGradingAnalysis, HslEntry, ParamContract } from "../api/types";
import { ColorGradingWheels } from "./ColorGradingWheels";
import { HslMixer } from "./HslMixer";
import { SliderControl } from "./SliderControl";
import { StrengthSlider } from "./StrengthSlider";
import { ToneCurve } from "./ToneCurve";

describe("参数控件", () => {
  it("滑杆直接使用契约边界并提供数值输入和复位", () => {
    const html = renderToStaticMarkup(
      <SliderControl
        label="曝光"
        rule={{ min: -5, max: 5, default: 0 }}
        value={1.25}
        onChange={() => undefined}
      />,
    );

    expect(html).toContain('min="-5"');
    expect(html).toContain('max="5"');
    expect(html).toContain('value="1.25"');
    expect(html).toContain('aria-label="重置曝光"');
  });

  it("全局强度按百分比展示", () => {
    const html = renderToStaticMarkup(<StrengthSlider factor={0.7} onChange={() => undefined} />);
    expect(html).toContain("70%");
    expect(html).toContain('value="70"');
  });

  it("HSL 渲染八个通道和当前通道三项控制", () => {
    const colors = ["red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"];
    const contract: ParamContract = {};
    const value: HslEntry[] = colors.map((color) => {
      for (const field of ["hue", "saturation", "luminance"]) {
        contract[`hsl.${color}.${field}`] = { min: -100, max: 100, default: 0 };
      }
      return { color, hue: 0, saturation: 0, luminance: 0 };
    });
    const html = renderToStaticMarkup(
      <HslMixer contract={contract} value={value} onChange={() => undefined} />,
    );

    expect(html.match(/role="tab"/g)).toHaveLength(8);
    for (const label of ["色相", "饱和度", "明亮度"]) {
      expect(html).toContain(`data-control-label="${label}"`);
    }
  });

  it("分级渲染四区选择器并读取各区契约", () => {
    const contract: ParamContract = {};
    for (const zone of ["shadows", "midtones", "highlights", "global"]) {
      contract[`color_grading.${zone}.hue`] = { min: 0, max: 360, default: 0 };
      contract[`color_grading.${zone}.saturation`] = { min: 0, max: 100, default: 0 };
      contract[`color_grading.${zone}.luminance`] = { min: -100, max: 100, default: 0 };
    }
    contract["color_grading.blending"] = { min: 0, max: 100, default: 50 };
    contract["color_grading.balance"] = { min: -100, max: 100, default: 0 };
    const zone = { hue: 0, saturation: 0, luminance: 0 };
    const value: ColorGradingAnalysis = {
      shadows: zone, midtones: zone, highlights: zone, global_: zone, blending: 50, balance: 0,
    };
    const html = renderToStaticMarkup(
      <ColorGradingWheels contract={contract} value={value} onChange={() => undefined} />,
    );

    for (const label of ["阴影", "中间调", "高光", "全局"]) expect(html).toContain(`>${label}<`);
    expect(html.match(/react-colorful/g)?.length).toBeGreaterThanOrEqual(4);
    expect(html).toContain('data-control-label="混合"');
    expect(html).toContain('data-control-label="平衡"');
  });

  it("曲线显示采样路径和全部控制点", () => {
    const html = renderToStaticMarkup(
      <ToneCurve
        value={[{ input: 0, output: 0 }, { input: 128, output: 150 }, { input: 255, output: 255 }]}
        onChange={() => undefined}
      />,
    );

    expect(html).toContain('aria-label="色调曲线"');
    expect(html.match(/<circle/g)).toHaveLength(3);
    expect(html).toContain("双击曲线区域添加控制点");
  });
});
