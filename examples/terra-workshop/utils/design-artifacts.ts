import type { DesignSystem } from "../types/design-system.ts";

export function buildDesignArtifacts(design: DesignSystem) {
  const { colors, typography, spacing, shadows } = design.tokens;
  const fontSize = Object.fromEntries(["xs", "base", "lg", "xl", "2xl", "3xl", "4xl"].map((name, index) => [name, `${Math.round(parseFloat(typography.baseFontSize) * typography.scaleRatio ** (index - 1) * 100) / 100}px`]));
  const config = {
    darkMode: "class",
    content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./src/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}", "./pages/**/*.{js,ts,jsx,tsx,mdx}"],
    theme: { extend: {
      colors: { ...colors, primary: { DEFAULT: colors.primary, foreground: colors.primaryForeground }, muted: { DEFAULT: colors.muted, foreground: colors.mutedForeground } },
      fontFamily: { sans: typography.fontFamilySans, mono: typography.fontFamilyMono }, fontSize,
      borderRadius: { lg: spacing.radius, md: `max(0px, calc(${spacing.radius} - 2px))`, sm: `max(0px, calc(${spacing.radius} - 4px))` },
      spacing: { container: spacing.containerPadding }, boxShadow: shadows,
    } }, plugins: [],
  };
  const cursorRules = `# ${design.meta.themeName} · VibeDesign
${design.meta.description}
目标用户：${design.meta.targetAudience}

## 必须执行的设计约束
${Object.entries(colors).map(([name, hex]) => `- ${name}: ${hex}`).join("\n")}
- 使用 bg-background、text-foreground、bg-primary、text-primary-foreground、bg-muted、text-muted-foreground、border-border；禁止任意品牌色替代令牌。
- 主字体：${typography.fontFamilySans}；等宽字体：${typography.fontFamilyMono}。
- 基础字号：${typography.baseFontSize}；字阶比例：${typography.scaleRatio}；尺寸序列：${Object.values(fontSize).join(" / ")}。
- 容器使用 p-container，即 ${spacing.containerPadding}；基础圆角 rounded-lg，即 ${spacing.radius}；衍生圆角不得为负。
- 卡片使用 shadow-card (${shadows.card})，浮层使用 shadow-popover (${shadows.popover})。
- 为表单关联 label，图标按钮提供名称，保留键盘焦点。按业务提供加载、空、错误和禁用状态；禁止用空处理函数冒充完成。
- 保留目标工程现有业务逻辑、扫描路径和插件，仅合并需要的主题配置。以上实际令牌优先于下方自然语言说明。

## 场景设计规则
${design.cursorRulesContent}

## 编辑器执行指令
请严格使用上述色彩变量和圆角规范，立刻更新或生成目标 React/Tailwind 代码；在用户授权的目标文件范围内实施，并完成适用的类型、构建与交互检查。
`;
  return { tailwindConfig: `import type { Config } from "tailwindcss";\n\nexport default ${JSON.stringify(config, null, 2)} satisfies Config;\n`, cursorRules };
}
