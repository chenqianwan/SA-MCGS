# Figma 定稿示意图正文替换（2026-09-29）

已将作者确认的两张 Figma 定稿图替换到正文。仅修改 `paper/latex/acl_latex.tex` 中两个图片文件引用；原图注、图号、正文、修订标记和实验结果保持不变。

- Figure 1：SA-MCGS framework，Figma 节点 `1:272`。已采用统一排版及底部横排问题说明。
- Figure 2：Motivation and comparison，Figma 节点 `1:2`。已采用居中树图、横排说明、流程间距调整，并删除确认不需要的孤立黑箭头。

## 导出与可复现性

本次 Figma Starter MCP 套餐限制阻止了新的矢量导出。嵌入的是本对话最后一次已确认 Figma 编辑结果返回的原始 PNG，1549 × 756 像素，未裁切、重绘或放大。源画布为 2212 × 1080，返回比例为 0.7。两份完整 PNG、节点号和 SHA-256 已记录在 `exports/` 及 `export_manifest.json`。

正文仍直接引用 PNG，没有将位图包装为矢量 PDF。若以后需要矢量图，须从同一 Figma 定稿节点重新导出。

## 编译与检查

使用 `/opt/homebrew/bin/tectonic --only-cached --keep-logs` 分别编译 `acl_latex.tex` 和 `acl_latex_clean.tex`。

- 修订标记版：27 页；净稿：25 页，均与替换前相同。
- 两版 Figure 1 和 Figure 2 均在第 3、4 页。
- PDF 内嵌图片的解码 RGB 数据与定稿 PNG 逐字节一致。CalRGB 提取转换会改变显示颜色数值，因此比较的是解码后的原始图像流。
- 无 overfull、未定义引用、缺字或编译错误；保留原有 underfull 与字体替代提示。
- 两版图页均已渲染检查，图注、编号及周边文字无裁切或重叠。

检查明细见 `verification.json`，渲染页面位于 `qa/`；替换前正文与 PDF 备份位于 `before/`。
