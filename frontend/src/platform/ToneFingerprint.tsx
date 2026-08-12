import { useId } from "react";
import type { TemplateCard } from "../api/types";

type ToneFingerprintProps = {
  template: TemplateCard;
  compact?: boolean;
};

function coordinate(value: number, index: number): number {
  const direction = value < 0 ? -1 : 1;
  return 50 + direction * Math.min(34, Math.abs(value) * 0.65 + index * 2);
}

export function ToneFingerprint({ template, compact = false }: ToneFingerprintProps) {
  const gradientId = `tone-${useId().replace(/:/g, "")}`;
  const values = template.key_parameters.length > 0
    ? template.key_parameters.map((item) => item.value)
    : [0, 0, 0];
  const points = values.slice(0, 6).map((value, index) => {
    const x = 10 + (index * 80) / Math.max(1, Math.min(values.length, 6) - 1);
    const y = coordinate(value, index);
    return `${x},${y}`;
  }).join(" ");

  return (
    <svg className="tone-fingerprint" viewBox="0 0 100 75" role="img" aria-label={`${template.name}的白盒参数指纹`}>
      <title>{template.name}的白盒参数指纹，不是照片效果图</title>
      <defs>
        <linearGradient id={gradientId} x1="0" x2="1">
          <stop offset="0" stopColor="#477b79" />
          <stop offset=".5" stopColor="#b7a36d" />
          <stop offset="1" stopColor="#b65d3d" />
        </linearGradient>
      </defs>
      <rect width="100" height="75" fill="#1b1a18" />
      <g opacity=".22" stroke="#d7d0c6" strokeWidth=".45">
        <path d="M10 15H90M10 37.5H90M10 60H90" />
        <path d="M25 8V67M50 8V67M75 8V67" />
      </g>
      <path d={`M10 50 L${points} L90 50`} fill="none" stroke={`url(#${gradientId})`} strokeWidth={compact ? 2.2 : 1.8} />
      {values.slice(0, 6).map((value, index) => {
        const count = Math.min(values.length, 6);
        const x = 10 + (index * 80) / Math.max(1, count - 1);
        return <circle key={`${index}-${value}`} cx={x} cy={coordinate(value, index)} r={compact ? 2.4 : 2} fill="#faf7f0" stroke="#b65d3d" strokeWidth="1" />;
      })}
      <rect x="10" y="66" width="80" height="2" rx="1" fill={`url(#${gradientId})`} opacity=".75" />
    </svg>
  );
}
