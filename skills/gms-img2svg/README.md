# gms-img2svg

在 Codex 中把标志、图表、插画和线稿转为可编辑 SVG。转换与校验均在本机运行；语义重建由当前智能体审阅几何、文字和对象关系。

## 安装

需要 Node.js 22.18+、Python 3.10+ 和系统 Cairo 库（例如 macOS 上运行 `brew install cairo`）。

```sh
npx --yes github:gmleong/gmskills#main install gms-img2svg
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r ~/.agents/skills/gms-img2svg/scripts/requirements-refine.txt
python ~/.agents/skills/gms-img2svg/scripts/doctor.py
```

如果安装器输出的是其他目录，请将以上技能路径替换为实际安装路径。只需轮廓描摹时，可安装较小的 `requirements.txt`；区域重建和双渲染检查使用 `requirements-refine.txt`。

## 使用

在 Codex 中提供图片并调用：

```text
$gms-img2svg 把这张图转换成可编辑的 SVG，保留文字和图层，检查原图与渲染结果。
```

也可以直接运行本机轮廓描摹：

```sh
python ~/.agents/skills/gms-img2svg/scripts/run_pipeline.py input.png \
  --contract contour-faithful --output-dir svg-job
```

结果在 `svg-job/final.svg`，对比图和检查报告在 `svg-job/qa/`。直接描摹将图中文字转为轮廓路径；需要可编辑文字、命名对象和原生图形时，使用 Codex 审阅并执行 [语义重建流程](references/workflow.md)。低清图像的细节只能近似重建；本包未捆绑超分模型或网页工作台。

## 许可证

技能代码采用仓库 [MIT 许可证](../../LICENSE)。捆绑的 [WASM 运行时声明](scripts/vendor/NOTICE.txt) 和 [VTracer 许可证](scripts/vendor/vtracer_v1/LICENSE-MIT) 随包分发。
