# 专家标注前端

## 当前标注选项：二选一判断

单文件页使用 `binary_judgment_v1`，只保留每个案例的三项判断：**存在／不存在**、**充分／不充分**、信心 1～5 分。充分性指“材料是否足够支持上述判断”，存入新字段 `judgment_sufficient`，不与旧 `evidence_sufficient` 混用。

逐段保留最小证据集和修复材料集两个勾选；前者必须包含于后者。角色分类和备注折叠选填；“更多上下文”不再单独提问。底部“确认并保存”代表已检查本例段落选择，自动保存和导出不替专家确认；再次修改答案需重新确认。

不充分案例记录原始二选一答案，但标记为待复核，不进入确定正例、负例或误报率分母。旧标注逐条原样保留，旧“部分充分／不适用”不自动映射成新二选一；旧 12-case 标签及原盲版均不修改。更新前的辅助页备份为 `../dist/sa_mcgs_assisted_annotation.before_binary.html`。

导出保留每条标注的协议字段、确认状态、判断充分性及适用性；新旧数据不得静默混算。`analysis_v1` 提供新协议的校验及单例指标函数；旧正式盲标合并链仍拒绝辅助数据和未经适配的新协议，后续汇总须按实际标注条件独立合并、裁决与冻结，不能将本页导出冒充旧盲标协议。

测试：`node tools/smoke_binary_standalone.js`（真实离线浏览器；需 Playwright）。

## 当前单文件版：提示直接显示（2026-09-17）

实际被注入修改的段落在段落编号旁显示“注入段落”。标记由同源 pre/post 冻结文本差异生成，按稳定节点身份映射；不把关联上下文或算法选中节点当作注入处。未注入材料不标记，标记不自动勾选答案。导出顶层记录页面标记版本，实际编辑记录另存 `injection_marker_pack_hash`；原有答案不追溯修改。隐藏算法提示不隐藏注入标记，本页仍为非盲辅助复核。

按要求，`../dist/sa_mcgs_blind_annotation.html` **保留原路径，但内容现在是带算法提示的辅助复核版，不再是盲标版**。双击即可离线使用，无需服务器或手动加载 JSON。每段直接显示 LEA、SA-MCGS 在 GPT-4o、Gemini 2.5 Pro 上的结果，并显示未注入/注入后条件。

- 提示已接入 **2026-09-09 的未注入 SA-MCGS 补跑结果**，替换 21 个旧失败结果；注入后结果与其他既有可用结果不变。真实未通过校验的输出仍明确标记，不作无风险或零分处理。
- 样本、中文材料、专家顺序和表单不变；自动复制兼容的原盲版浏览器进度到独立存储，原记录不覆盖。也支持导入原盲版 JSON。
- 本页保存和导出均标记为 `method_assisted_review`，附提示包哈希；收起提示不改变此标记。
- 更新前的辅助页进度会自动复制接续，原存储不覆盖；可导入旧版辅助页备份。导出 `hint_pack_history` 记录新旧提示版本。
- 未注入 SA-MCGS 目前 33/36 个模型—样本结果可用，LEA 为 35/36；剩余 4 个无效结果不隐藏、不用注入后结果代替。
- 原 HTML 备份为 `../dist/sa_mcgs_blind_annotation.original.html`；旧 `sa_mcgs_blind_annotation_pack.zip` 未改动。
- 新单文件压缩包：`../dist/sa_mcgs_assisted_annotation_pack.zip`。

重建与测试（不调用模型）：

```bash
python3 tools/build_method_hints.py
python3 tools/build_assisted_standalone.py
node tools/smoke_assisted_standalone.js ../dist/sa_mcgs_assisted_annotation.before_binary.html
node tools/smoke_binary_standalone.js
```

上述旧辅助版 smoke 对更新前备份运行；二选一版本使用 `smoke_binary_standalone.js`，原盲版 source smoke 保持不变。

## 原正式盲标版（独立盲法流程使用）

正式版本是单个离线 HTML，不载入样本条件、算法结果或私有映射。它包含本轮需要新增标注的 42 个展示样本、648 个段落；旧 12 个已有完整三专家结果的样本不重复标注。

```bash
python3 tools/build_blind_standalone.py
python3 tools/validate_blind_standalone.py
node tools/smoke_blind_frontend.js
```

以下是原盲版构建命令的输出；**重新运行盲版构建器会覆盖上述同名辅助页**。需要保留当前提示时请勿运行：

- `../dist/sa_mcgs_blind_annotation.html`：可直接双击使用；
- `../dist/BLIND_ANNOTATION_README_ZH.txt`：分发说明；
- `../dist/sa_mcgs_blind_annotation_pack.zip`：给专家的完整压缩包。

页面为三位专家使用冻结的独立随机顺序；进度按专家编号保存在浏览器本地，可导出/恢复 JSON 备份，并可导出当前专家的 XLSX 与 CSV。正式标注期间不要打开下述辅助页。

## 原多文件辅助复核版（保留）

当前页面包含 **42 个展示样本**：18 个未注入原始样本与 24 个注入后样本。两种条件都直接显示；实际打标时是否隐藏，由打标流程控制。

页面默认显示中文译文，并在每个段落下展示 GPT-4o、Gemini 2.5 Pro 的 LEA 与 SA-MCGS 提示：是否进入算法结果子图、风险相关分和 SCC 内排名。原文仅放在折叠核对区。页面导出会记录翻译包与提示包哈希。

## 数据文件

- `data/manifest.json`：冻结的 42 个专家展示样本；
- `data/translations_zh.json`：逐段中文译文；
- `data/method_hints.json`：逐段 LEA/SA-MCGS 提示；
- `data/translation_cache_zh.json`：可恢复的翻译缓存，不进入分发包；
- `../internal/private_codebook.json`：稳定 ID 私有映射，不进入分发包。

重新生成辅助数据：

```bash
python3 tools/build_translation_pack.py
python3 tools/normalize_translation_pack.py
python3 tools/build_method_hints.py
```

提示构建器通过私有映射表稳定匹配结果，并强制核验 SCC 节点集合。默认合并 9 月 9 日补跑的未注入 SA-MCGS 结果，保留旧首试记录和历史提示包以便追溯；未通过校验的结果仍显示“暂无可靠提示”，不会借用注入后输出。重建提示包不调用模型接口。

## 运行

```bash
python3 -m http.server 8765
```

打开 `http://127.0.0.1:8765/`。页面在浏览器本地自动保存；建议结束时同时导出电子表格和完整备份。

## 验证与打包

```bash
# 当前预览包：允许明确标出的模型运行失败项
python3 tools/validate_expert_pack.py --frontend . --allow-incomplete-results

# 补跑完成后的正式检查：不得有方法缺少可用模型
python3 tools/validate_expert_pack.py --frontend .
node --check app.js
node tools/smoke_frontend.js

python3 tools/package_expert_frontend.py \
  --frontend . \
  --allow-incomplete-results \
  --out ../dist/expert_annotation_pack.zip
```

验证器检查 42/42 个展示样本、648/648 个段落的中文与提示结构，拒绝身份错配、构造模板和参考答案字段泄漏。正式检查还要求每种方法在每段至少有一个可用模型结果。

## 口径

该版本是 **算法辅助复核页面**。页面保留全部算法结果；若实际打标时隐藏提示，应在实验记录中说明隐藏方式。
