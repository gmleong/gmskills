# gmskills

GM 的开源 Codex Skill 集合。每个 Skill 可单独安装，按需选用。

## Skill 列表

| Skill | 用途 |
| --- | --- |
| [`gms-vibedesign`](#gms-vibedesign) | 从产品需求和业务代码生成设计系统与可运行页面 |
| [`gms-img2svg`](#gms-img2svg) | 在本机把图像转换为可编辑 SVG |

## gms-vibedesign

把产品调性和业务需求变成配色、字体、间距等设计令牌，再用这些规范生成或改进页面。适合从零建立设计系统，也适合给已有产品做界面调整。

```sh
npx --yes github:gmleong/gmskills#v0.2.0 install gms-vibedesign
```

安装后在 Codex 中调用 `$gms-vibedesign`。[使用教程](docs/usage-guide.md) · [可运行示例](examples/terra-workshop/) · [Skill 源码](skills/gms-vibedesign/)

## gms-img2svg

把标志、图表、插画和线稿转成可编辑 SVG。可以直接描摹原图轮廓，也可以由 Codex 审阅后重建文字、形状和对象关系。转换与渲染检查在本机运行。

```sh
npx --yes github:gmleong/gmskills#main install gms-img2svg
```

配置 Python 和 Cairo 后，在 Codex 中调用 `$gms-img2svg`。[安装与使用](skills/gms-img2svg/README.md) · [Skill 源码](skills/gms-img2svg/)

## 许可证

[MIT 许可证](LICENSE) · 随附的 [VTracer 运行时](skills/gms-img2svg/scripts/vendor/) 保留各自的许可证和声明。
