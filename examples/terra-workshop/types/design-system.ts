import { z } from "zod";
import { getSaturation, MAX_SATURATION } from "../utils/aesthetic-eval.ts";

const text = (maximum: number) => z.string().trim().min(1).max(maximum);
const color = z.string().regex(/^#[0-9a-fA-F]{6}$/, "颜色必须是 #RRGGBB");
const font = text(400).regex(/^[\p{L}\p{N}\s"',._-]+$/u, "字体栈包含无效字符");
const pixels = (minimum: number, maximum: number) => z.string()
  .regex(/^\d+(?:\.\d+)?px$/, "尺寸必须使用非负 px 值")
  .refine((value) => parseFloat(value) >= minimum && parseFloat(value) <= maximum,
    `尺寸必须在 ${minimum}–${maximum}px 范围内`);
const shadowLayer = String.raw`(?:inset\s+)?(?:(?:-?\d+(?:\.\d+)?px|0)\s+){2,4}(?:#[0-9a-fA-F]{6}|rgba?\([\d.,% /]+\))`;
const shadow = text(500).regex(new RegExp(`^(?:none|${shadowLayer}(?:,\\s*${shadowLayer})*)$`), "阴影需为 none 或 px 尺寸加 Hex/rgb/rgba 颜色");

export const DesignSystemBaseSchema = z.strictObject({
  meta: z.strictObject({
    themeName: text(80).describe("设计系统名称"),
    description: text(800).describe("设计哲学、调性和布局原则"),
    targetAudience: text(300).describe("目标用户和场景"),
  }),
  tokens: z.strictObject({
    colors: z.strictObject({
      background: color.describe("画布底色"),
      foreground: color.describe("正文颜色"),
      primary: color.describe("主按钮及品牌链接颜色"),
      primaryForeground: color.describe("主按钮文字"),
      secondary: color.describe("次级表面，搭配 foreground"),
      muted: color.describe("弱化背景表面"),
      mutedForeground: color.describe("辅助文字，需在 background 和 muted 上可读"),
      border: color.describe("边框"),
      accent: color.describe("装饰性强调色，不自动视作合格文字颜色"),
    }),
    typography: z.strictObject({
      fontFamilySans: font.describe("完整无衬线字体栈，含系统字体回退"),
      fontFamilyMono: font.describe("完整等宽字体栈"),
      baseFontSize: pixels(12, 24).describe("基础正文字号，建议 16px"),
      scaleRatio: z.number().finite().min(1.067).max(1.618).describe("数值型字阶比例，例如 1.25；不可输出字符串"),
    }),
    spacing: z.strictObject({
      radius: pixels(0, 32).describe("基础圆角"),
      containerPadding: pixels(8, 64).describe("实际容器留白"),
    }),
    shadows: z.strictObject({ card: shadow, popover: shadow }),
  }),
  cursorRulesContent: text(12000).min(30).describe("具体可执行的颜色、字阶、间距、布局及交互规范；与 tokens 一致"),
});

export type DesignSystem = z.infer<typeof DesignSystemBaseSchema>;

export const DesignSystemSchema = DesignSystemBaseSchema.superRefine((theme, context) => {
  for (const [name, hex] of Object.entries(theme.tokens.colors)) {
    if (getSaturation(hex) > MAX_SATURATION) {
      context.addIssue({ code: "custom", path: ["tokens", "colors", name], message: `HSL 饱和度不可超过 ${MAX_SATURATION * 100}%` });
    }
  }
});
