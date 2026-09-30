# 设计系统数据契约

延续用户提供的 `DesignSystemSchema`，字段名称保持兼容。下面的值仅用于解释结构，不是固定主题；根据具体业务与调性生成。

```json
{
  "meta": {
    "themeName": "Quiet Workspace",
    "description": "适合长时间阅读的清晰、中性工作界面",
    "targetAudience": "管理复杂业务记录的团队"
  },
  "tokens": {
    "colors": {
      "background": "#F8FAFC",
      "foreground": "#172033",
      "primary": "#3730A3",
      "primaryForeground": "#FFFFFF",
      "secondary": "#E2E8F0",
      "muted": "#EEF2F6",
      "mutedForeground": "#526175",
      "border": "#CBD5E1",
      "accent": "#3730A3"
    },
    "typography": {
      "fontFamilySans": "Inter, system-ui, sans-serif",
      "fontFamilyMono": "ui-monospace, SFMono-Regular, monospace",
      "baseFontSize": "16px",
      "scaleRatio": 1.25
    },
    "spacing": {
      "radius": "8px",
      "containerPadding": "24px"
    },
    "shadows": {
      "card": "0 2px 8px rgb(23 32 51 / 0.06)",
      "popover": "0 12px 32px rgb(23 32 51 / 0.12)"
    }
  },
  "cursorRulesContent": "具体到该设计系统的排版、间距、颜色、交互状态与组件约束。"
}
```

## 字段约束

- 所有字段必须存在；`meta`、字体、尺寸、阴影与规则内容均为非空字符串。
- 九个颜色字段采用 `#RRGGBB`，不使用透明色、简写或 CSS 变量作为 JSON 中的颜色值。
- `baseFontSize`、`radius`、`containerPadding` 使用明确单位。`scaleRatio` 是 1.067–1.618 的数值，按 baseFontSize × scaleRatio^n 推导字号，并在工程约束中列出实际序列。
- `secondary` 没有独立的前景字段，若将 `foreground` 用在它上面，应另算该配对的对比度；`accent` 同理。装饰性色与文字背景的要求不同。
- `.cursorrules` 是这套设计系统的工程约束，不能用泛化的“全部 p-6”覆盖实际 `containerPadding`。

## 样式映射

Tailwind CSS 3 中保持 `bg-background`、`text-foreground`、`bg-primary`、`text-primary-foreground`、`bg-muted`、`text-muted-foreground`、`border-border`、`shadow-card` 等语义类可用。基础圆角映射到 `rounded-lg`；衍生圆角不得变成负数。保留目标工程原有 content 扫描路径和插件。

导出代码时使用 JSON 编码或正确的字符串转义，避免含引号的字体栈导致配置语法错误。只生成项目确实会用到的配置，不额外创建组件库或设计系统运行时。

业务页面输入沿用 `{ sourceCode, designSystem, pageType? }` 的概念，但智能体可以直接读取文件，无需构造 HTTP 请求。页面输出中的 `reactCode` 是完整源代码，不含 Markdown 围栏；普通文件交付直接保存为 `.tsx`。
