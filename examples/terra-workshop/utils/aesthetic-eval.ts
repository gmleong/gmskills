import type { DesignSystem } from "../types/design-system.ts";

// Product heuristic, not a WCAG rule or a universal measure of aesthetic quality.
export const MAX_SATURATION = 0.85;
export const CONTRAST_THRESHOLDS = { AA: 4.5, AAA: 7 } as const;

function rgb(hex: string): [number, number, number] {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) throw new TypeError("颜色必须是 #RRGGBB");
  return [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16) / 255) as [number, number, number];
}

export function relativeLuminance(hex: string): number {
  const linear = rgb(hex).map((channel) => channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4);
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

export function contrastRatio(foreground: string, background: string): number {
  const values = [relativeLuminance(foreground), relativeLuminance(background)].sort((a, b) => a - b);
  return (values[1] + 0.05) / (values[0] + 0.05);
}

export function passesContrast(foreground: string, background: string, level: keyof typeof CONTRAST_THRESHOLDS = "AA"): boolean {
  return contrastRatio(foreground, background) >= CONTRAST_THRESHOLDS[level];
}

export function getSaturation(hex: string): number {
  const channels = rgb(hex);
  const maximum = Math.max(...channels);
  const minimum = Math.min(...channels);
  const delta = maximum - minimum;
  return delta === 0 ? 0 : delta / (1 - Math.abs(maximum + minimum - 1));
}

export type AestheticEvaluation = {
  passed: boolean;
  grade: "AA" | "AAA" | "FAIL";
  contrast: { foreground: string; background: string; ratio: number; passed: boolean; aaa: boolean }[];
  saturation: { token: string; value: number; passed: boolean }[];
  typeScale: number[];
  suggestions: string[];
};

export function evaluateDesignSystem(theme: DesignSystem): AestheticEvaluation {
  const colors = theme.tokens.colors;
  const pairs: [keyof typeof colors, keyof typeof colors][] = [
    ["foreground", "background"], ["mutedForeground", "background"],
    ["foreground", "muted"], ["mutedForeground", "muted"],
    ["primaryForeground", "primary"], ["foreground", "secondary"],
    ["primary", "background"],
  ];
  const contrast = pairs.map(([foreground, background]) => {
    const ratio = contrastRatio(colors[foreground], colors[background]);
    return { foreground, background, ratio, passed: ratio >= 4.5, aaa: ratio >= 7 };
  });
  const saturation = Object.entries(colors).map(([token, hex]) => {
    const value = getSaturation(hex);
    return { token, value, passed: value <= MAX_SATURATION };
  });
  const suggestions = [
    ...contrast.filter((check) => !check.passed).map((check) => `${check.foreground}/${check.background} 对比度 ${check.ratio.toFixed(3)}:1，正文需 ≥4.5:1；请加深文字或调整背景明度。`),
    ...saturation.filter((check) => !check.passed).map((check) => `${check.token} 的 HSL 饱和度 ${(check.value * 100).toFixed(1)}%，超过产品阈值 85%；请降低饱和度。`),
  ];
  const base = parseFloat(theme.tokens.typography.baseFontSize);
  const ratio = theme.tokens.typography.scaleRatio;
  if (!Number.isFinite(base) || base < 12 || base > 24 || !Number.isFinite(ratio) || ratio < 1.067 || ratio > 1.618) {
    suggestions.push("基础字号需为 12–24px，字阶比例需为 1.067–1.618 的数值。");
  }
  const passed = suggestions.length === 0;
  return {
    passed,
    grade: !passed ? "FAIL" : contrast.every((check) => check.aaa) ? "AAA" : "AA",
    contrast,
    saturation,
    typeScale: Array.from({ length: 7 }, (_, index) => Math.round(base * ratio ** (index - 1) * 100) / 100),
    suggestions,
  };
}
