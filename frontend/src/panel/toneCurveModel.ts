import type { ToneCurvePoint } from "../api/types";

const clampByte = (value: number) => Math.min(255, Math.max(0, Math.round(value)));

export function addCurvePoint(
  points: readonly ToneCurvePoint[],
  point: ToneCurvePoint,
): ToneCurvePoint[] {
  const next = { input: clampByte(point.input), output: clampByte(point.output) };
  return [...points.filter((item) => item.input !== next.input), next]
    .sort((left, right) => left.input - right.input);
}

export function moveCurvePoint(
  points: readonly ToneCurvePoint[],
  index: number,
  point: ToneCurvePoint,
): ToneCurvePoint[] {
  if (!points[index]) return [...points];
  const previous = points[index - 1];
  const following = points[index + 1];
  const fixedInput = index === 0
    ? points[0].input
    : index === points.length - 1
      ? points[index].input
      : Math.min(following.input - 1, Math.max(previous.input + 1, clampByte(point.input)));
  return points.map((item, itemIndex) => itemIndex === index
    ? { input: fixedInput, output: clampByte(point.output) }
    : item);
}

export function removeCurvePoint(
  points: readonly ToneCurvePoint[],
  index: number,
): readonly ToneCurvePoint[] {
  if (points.length <= 2 || index <= 0 || index >= points.length - 1) return points;
  return points.filter((_, itemIndex) => itemIndex !== index);
}

/** 用 Fritsch-Carlson 切线采样，避免单调控制点产生过冲。 */
export function sampleMonotoneCurve(
  points: readonly ToneCurvePoint[],
  sampleCount: number,
): ToneCurvePoint[] {
  if (points.length < 2) return [...points];
  const count = Math.max(2, Math.round(sampleCount));
  const slopes = points.slice(0, -1).map((point, index) =>
    (points[index + 1].output - point.output) / (points[index + 1].input - point.input));
  const tangents = points.map((_, index) => {
    if (index === 0) return slopes[0];
    if (index === points.length - 1) return slopes[slopes.length - 1] ?? 0;
    if (slopes[index - 1] * slopes[index] <= 0) return 0;
    return (slopes[index - 1] + slopes[index]) / 2;
  });

  for (let index = 0; index < slopes.length; index += 1) {
    if (slopes[index] === 0) {
      tangents[index] = 0;
      tangents[index + 1] = 0;
      continue;
    }
    const left = tangents[index] / slopes[index];
    const right = tangents[index + 1] / slopes[index];
    const length = Math.hypot(left, right);
    if (length > 3) {
      const scale = 3 / length;
      tangents[index] = scale * left * slopes[index];
      tangents[index + 1] = scale * right * slopes[index];
    }
  }

  return Array.from({ length: count }, (_, sampleIndex) => {
    if (sampleIndex === 0) return { ...points[0] };
    if (sampleIndex === count - 1) return { ...points[points.length - 1] };
    const input = points[0].input
      + (points[points.length - 1].input - points[0].input) * sampleIndex / (count - 1);
    let segment = 0;
    while (segment < points.length - 2 && input > points[segment + 1].input) segment += 1;
    const left = points[segment];
    const right = points[segment + 1];
    const width = right.input - left.input;
    const t = (input - left.input) / width;
    const t2 = t * t;
    const t3 = t2 * t;
    const output = (2 * t3 - 3 * t2 + 1) * left.output
      + (t3 - 2 * t2 + t) * width * tangents[segment]
      + (-2 * t3 + 3 * t2) * right.output
      + (t3 - t2) * width * tangents[segment + 1];
    return { input, output };
  });
}
