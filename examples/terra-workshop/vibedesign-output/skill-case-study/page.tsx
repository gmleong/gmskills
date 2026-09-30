"use client";

import Link from "next/link";
import { useState, type CSSProperties } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowUpRight, Check, ChevronRight, Code2, Copy, Layers, Palette, RotateCcw, Type } from "lucide-react";
import { DesignSystemSchema, type DesignSystem } from "../../types/design-system";
import { evaluateDesignSystem } from "../../utils/aesthetic-eval";
import { buildDesignArtifacts } from "../../utils/design-artifacts";
import initial from "./design-system.json";
import styles from "./page.module.css";

const colorNames = {
  background: "画布", foreground: "正文", primary: "主色", primaryForeground: "主色文字",
  secondary: "次级色", muted: "次级表面", mutedForeground: "辅助文字", border: "边框", accent: "强调色",
};
type ColorKey = keyof typeof colorNames;
type Artifact = "design-system.json" | "tailwind.config.ts" | ".cursorrules";
const fileNames: Artifact[] = ["design-system.json", "tailwind.config.ts", ".cursorrules"];
const fontOptions = [initial.tokens.typography.fontFamilySans, '"Helvetica Neue", Arial, sans-serif', '"SFMono-Regular", Consolas, monospace'];

function themeVariables(design: DesignSystem, prefix: string) {
  return Object.fromEntries([
    ...Object.entries(design.tokens.colors).map(([key, value]) => [`--${prefix}-${key}`, value]),
    [`--${prefix}-radius`, design.tokens.spacing.radius],
    [`--${prefix}-padding`, design.tokens.spacing.containerPadding],
    [`--${prefix}-font`, design.tokens.typography.fontFamilySans],
    [`--${prefix}-mono`, design.tokens.typography.fontFamilyMono],
    [`--${prefix}-base`, design.tokens.typography.baseFontSize],
    [`--${prefix}-heading`, `${parseFloat(design.tokens.typography.baseFontSize) * design.tokens.typography.scaleRatio ** 3}px`],
    [`--${prefix}-card`, design.tokens.shadows.card],
  ]) as CSSProperties;
}

export default function SkillCaseStudy() {
  const [mode, setMode] = useState<"baseline" | "designed">("designed");
  const [design, setDesign] = useState<DesignSystem>(initial);
  const [artifact, setArtifact] = useState<Artifact>("design-system.json");
  const [notice, setNotice] = useState("");
  const evaluation = evaluateDesignSystem(design);
  const validation = DesignSystemSchema.safeParse(design);
  const errors = [...new Set([
    ...(validation.success ? [] : validation.error.issues.map((issue) => issue.path.at(-1) === "themeName" ? "请输入方案名称（1–80 个字符）。" : `${colorNames[issue.path.at(-1) as ColorKey] || "设计规范"}：${issue.message}`)),
    ...evaluation.suggestions,
  ])];
  const canExport = errors.length === 0;
  const generated = buildDesignArtifacts(design);
  const files: Record<Artifact, string> = {
    "design-system.json": `${JSON.stringify({ ...design, cursorRulesContent: generated.cursorRules }, null, 2)}\n`,
    "tailwind.config.ts": generated.tailwindConfig,
    ".cursorrules": generated.cursorRules,
  };

  function editColor(key: ColorKey, value: string) {
    setDesign((previous) => ({ ...previous, tokens: { ...previous.tokens, colors: { ...previous.tokens.colors, [key]: value.toUpperCase() } } }));
    setNotice("");
  }
  function editSpacing(key: "radius" | "containerPadding", value: string) {
    setDesign((previous) => ({ ...previous, tokens: { ...previous.tokens, spacing: { ...previous.tokens.spacing, [key]: `${value}px` } } }));
    setNotice("");
  }
  function download() {
    if (!canExport) return;
    const url = URL.createObjectURL(new Blob([files[artifact]], { type: artifact.endsWith(".json") ? "application/json" : "text/plain;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = artifact;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(`已发起下载：${artifact}`);
  }
  async function copy() {
    if (!canExport) return;
    try {
      await navigator.clipboard.writeText(files[artifact]);
      setNotice(`已复制 ${artifact}`);
    } catch { setNotice("复制未成功，可选中下方代码手动复制。"); }
  }

  return (
    <div className={styles.page} style={themeVariables(initial, "ui")}>
      <a className={styles.skipLink} href="#workspace">跳至编辑工作台</a>
      <header className={styles.header}>
        <Link href="https://github.com/gmleong/gmskills" className={styles.brand}>vibedesign<span>®</span></Link>
        <span>FIELD NOTES / 001</span>
        <Link href="https://github.com/gmleong/gmskills#安装">获取 Skill <ArrowUpRight size={15} /></Link>
      </header>
      <main>
        <section className={styles.intro} aria-labelledby="case-title">
          <div><p className={styles.eyebrow}>由业务代码出发 / 可交互的设计对照</p><h1 id="case-title">同一份业务，<span>另一种秩序。</span></h1></div>
          <p>从 VibeDesign 自己的设计规范出发。<br />编辑、预览、校验、交付，一条完整的工作流。<br /><span>你可以直接改动下面的页面。</span></p>
        </section>

        <div className={styles.compareBar}>
          <div className={styles.modePicker} role="group" aria-label="页面设计对照">
            <button type="button" aria-pressed={mode === "baseline"} onClick={() => setMode("baseline")}>01 <span>常规布局</span></button>
            <button type="button" aria-pressed={mode === "designed"} onClick={() => setMode("designed")}>02 <span>VibeDesign</span></button>
          </div>
          <p>同一份数据 · 同一套功能 · 切换保留修改</p>
        </div>

        <section id="workspace" className={`${styles.workspace} ${mode === "baseline" ? styles.baseline : styles.designed}`} aria-label={`${mode === "designed" ? "VibeDesign" : "常规布局"}设计编辑器`}>
          <aside className={styles.rail}>
            <div className={styles.workspaceBrand}><Layers size={21} /><span>Atelier<span>DESIGN WORKSPACE</span></span></div>
            <p className={styles.railCaption}>工作空间</p>
            <nav aria-label="编辑器导航">
              <a href="#palette"><Palette size={16} />色彩规范<ChevronRight size={12} /></a>
              <a href="#typography"><Type size={16} />字体与空间</a>
              <a href="#delivery"><Code2 size={16} />开发交付</a>
            </nav>
            <div className={styles.railFoot}><span className={styles.avatar}>T</span><div>Terra Studio<small>本地交互案例</small></div></div>
          </aside>

          <div className={styles.canvas}>
            <div className={styles.breadcrumb}>我的设计系统 <ChevronRight size={12} /> <span>{design.meta.themeName || "未命名"}</span></div>
            <div className={styles.canvasHeading}><div><p className={styles.eyebrow}>A SYSTEM WITH A POINT OF VIEW</p><h2>{design.meta.themeName || "未命名设计"}<span>®</span></h2><p>将灵感里的温度，留在每一个细节。</p></div><span className={styles.version}>01 / EDITION</span></div>

            <section id="palette" className={styles.paletteSection} aria-labelledby="palette-heading">
              <div className={styles.sectionLabel}><h3 id="palette-heading">01 <span>色彩，有自己的关系。</span></h3><span>9 TOKENS</span></div>
              <div className={styles.paletteBand} aria-label="主要色彩预览">
                {(["primary", "background", "foreground", "secondary", "accent"] as ColorKey[]).map((key) => <div key={key} style={{ background: design.tokens.colors[key] }}><span>{colorNames[key]}</span></div>)}
              </div>
              <div className={styles.colorGrid}>
                {(Object.keys(colorNames) as ColorKey[]).map((key) => <label key={key} className={styles.colorField}><input aria-label={`${colorNames[key]}颜色`} type="color" value={design.tokens.colors[key]} onChange={(event) => editColor(key, event.target.value)} /><span>{colorNames[key]}<code>{design.tokens.colors[key]}</code></span></label>)}
              </div>
            </section>

            <section className={styles.previewSection} aria-labelledby="preview-heading">
              <div className={styles.sectionLabel}><h3 id="preview-heading">02 <span>落在界面上，才算设计。</span></h3><span>LIVE PREVIEW</span></div>
              <div className={styles.preview} style={themeVariables(design, "sample")}>
                <div className={styles.previewTop}><span>T / STUDIO</span><span>DESIGN NOTES — 001</span></div>
                <h4>好想法，<br />慢慢成形。</h4><p>留一点空间，让重要的内容被看见。</p>
                <div className={styles.previewBottom}><span>{design.meta.themeName || "未命名"}<small>你的下一次创作，从这里开始。</small></span><button type="button" onClick={download} disabled={!canExport}>导出主题<ArrowUpRight size={15} /></button></div>
              </div>
            </section>

            <section id="delivery" className={styles.delivery} aria-labelledby="delivery-heading">
              <div className={styles.sectionLabel}><h3 id="delivery-heading">03 <span>把好设计，带进代码。</span></h3><span>READY TO BUILD</span></div>
              <div className={styles.fileBar}><label htmlFor="artifact">交付文件<select id="artifact" value={artifact} onChange={(event) => setArtifact(event.target.value as Artifact)}>{fileNames.map((name) => <option key={name}>{name}</option>)}</select></label><button type="button" onClick={copy} disabled={!canExport}><Copy size={14} />复制代码</button><button type="button" onClick={download} disabled={!canExport}><ArrowDownToLine size={14} />下载文件</button></div>
              <pre tabIndex={0} aria-label={`${artifact} 代码`}><code>{files[artifact]}</code></pre>
              <p className={styles.deliveryNote}>修改仅保留在当前页面；导出文件可保存你的设计。{!canExport && "请先修复校验问题，再导出。"}</p>
            </section>
          </div>

          <aside className={styles.inspector} aria-label="设计属性">
            <div className={styles.inspectorHeading}><span>设计属性</span><span>PROPERTIES</span></div>
            <label className={styles.field} htmlFor="theme-name">方案名称<input id="theme-name" value={design.meta.themeName} maxLength={80} aria-invalid={!design.meta.themeName.trim()} onChange={(event) => { setDesign((previous) => ({ ...previous, meta: { ...previous.meta, themeName: event.target.value } })); setNotice(""); }} /></label>
            <section id="typography" className={styles.propertySection}>
              <h3><Type size={15} /> 字体与空间</h3>
              <label className={styles.field} htmlFor="font-family">界面字体<select id="font-family" value={design.tokens.typography.fontFamilySans} onChange={(event) => setDesign((previous) => ({ ...previous, tokens: { ...previous.tokens, typography: { ...previous.tokens.typography, fontFamilySans: event.target.value } } }))}>{fontOptions.map((font, index) => <option key={font} value={font}>{["Avenir · 现代无衬线", "Helvetica · 中性无衬线", "Mono · 等宽字体"][index]}</option>)}</select></label>
              <div className={styles.typeSample} style={{ fontFamily: design.tokens.typography.fontFamilySans }}><span>Aa</span><div>有节奏的表达<small>16px · × {design.tokens.typography.scaleRatio}</small></div></div>
              <label className={styles.rangeField} htmlFor="theme-radius"><span>圆角<output htmlFor="theme-radius">{design.tokens.spacing.radius}</output></span><input id="theme-radius" type="range" min="0" max="32" value={parseFloat(design.tokens.spacing.radius)} onChange={(event) => editSpacing("radius", event.target.value)} /></label>
              <label className={styles.rangeField} htmlFor="theme-padding"><span>容器留白<output htmlFor="theme-padding">{design.tokens.spacing.containerPadding}</output></span><input id="theme-padding" type="range" min="8" max="64" step="4" value={parseFloat(design.tokens.spacing.containerPadding)} onChange={(event) => editSpacing("containerPadding", event.target.value)} /></label>
            </section>

            <section className={styles.propertySection} aria-labelledby="checks-heading">
              <h3 id="checks-heading"><Check size={15} /> 正文配色检查</h3>
              <div className={styles.checkSummary} role="status"><strong>{evaluation.contrast.filter((check) => check.passed).length}<span> / 7</span></strong><span>配对达到 4.5:1<br /><small>随颜色实时计算</small></span></div>
              <details className={styles.checkDetails}><summary>查看每组对比度</summary><ul>{evaluation.contrast.map((check) => <li key={`${check.foreground}/${check.background}`}><span>{colorNames[check.foreground as ColorKey]} / {colorNames[check.background as ColorKey]}</span><span>{check.ratio.toFixed(2)} {check.passed ? "✓" : "×"}</span></li>)}</ul></details>
              <p className={styles.checkNote}>检查指定正文配对，非整页无障碍认证。</p>
            </section>
            {!canExport && <div role="alert" className={styles.error}><strong>暂不可导出</strong><ul>{errors.map((error) => <li key={error}>{error}</li>)}</ul></div>}
            <button type="button" className={styles.reset} onClick={() => { setDesign(initial); setNotice("已恢复 Terra Workshop 初始规范。"); }}><RotateCcw size={13} />恢复初始规范</button>
            <div className={styles.localNote}><span>由智能体直接生成</span><p>当前页面本地编辑与校验，<br />不调用模型服务。</p></div>
          </aside>
        </section>

        <section className={styles.method} aria-labelledby="method-heading">
          <div><p className={styles.eyebrow}>关于这次对照</p><h2 id="method-heading">功能相同，<br />设计判断不同。</h2></div>
          <div><h3>业务来自哪里？</h3><p>来自本项目的 DesignSystemSchema、审美校验器与代码导出函数。没有编造订单或营收；这是内部产品案例，不是客户案例。</p></div>
          <div><h3>如何比较？</h3><p>常规版使用标准表单布局，Skill 版采用暖色设计规范与任务分区。两版共享组件、数据和全部操作，由同一智能体实现，不是独立模型盲测。</p></div>
          <div><h3>带到你的项目。</h3><p>把业务代码交给智能体，再调用 VibeDesign。设计方向可以变，业务和功能要保持完整。</p><Link href="https://github.com/gmleong/gmskills#安装">安装并开始 <ArrowUpRight size={15} /></Link></div>
        </section>
        <footer className={styles.footer}><Link href="https://github.com/gmleong/gmskills"><ArrowLeft size={14} />返回 VibeDesign</Link><span>A little more intention.</span></footer>
      </main>
      <div role="status" aria-live="polite" className={styles.notice}>{notice && <span>{notice}<button type="button" aria-label="关闭通知" onClick={() => setNotice("")}>×</button></span>}</div>
    </div>
  );
}
