# 新增 citation 逐条核对报告

核对日期：2026-10-01。对象：本轮修订新增的五条模型出处，以及这些引用在 §4.4 中的实际用途。

**结论：五条文献／模型卡都真实存在，都与文中的模型对应，没有发现假文献或引用错模型。实际修正集中在作者元数据；另外完善了团队署名和来源版本。五条标题、年份、arXiv 编号及已有 DOI 均通过核对。**

已将确认的调整落入论文：四条书目发生变化，GPT-4o 原条目保留。本次没有改写正文论点或实验内容。净稿正文仍在第 8 页结束，Limitations 从第 9 页开始；全文 24 页，修订版 29 页。

## 1. 核对范围与方法

先将当前版本与 `2026NAACL/SA-MCGS/backups/latex_2026-09-22` 对照，并用 Git 提交 `c6d486c` 交叉检查新增范围。新增书目键和新引入文献的引用键一致，共五条。五条引用都出现在主文件 §4.4 的模型介绍段；当前净稿位置为第 6 页。

本次没有把“链接能打开”作为核对完成的标准。逐条检查了：

1. 原始文献是否存在，是否来自模型提供方或作者的正式公开渠道。
2. 完整标题、模型名称、版本和参数规模是否匹配。
3. 报告首页署名、贡献者名单和自动导出作者元数据是否一致。
4. 首发年份、修订年份、模型发布日期是否被混淆。
5. arXiv 编号、DOI、链接是否指向同一份材料。
6. 文献类型和出版状态是否准确，有无应优先采用的正式发表版本。
7. 原文具体章节是否支持论文中引用它的那句话。
8. 官方报告、模型卡与本地模型配置能否对应；对本地记录只作出处核对，不重新运行实验。
9. BibTeX 作者字段在现有 ACL 样式中的实际输出是否正常。
10. 修改后正文引用、参考文献、链接、修订颜色和分页是否正确。

“新增”在这里指本轮新引入的文献条目。原来已经存在的全部参考文献不属于本次逐篇审计范围；本报告不把五条审计扩大成对全库文献的背书。

## 2. 五条引用总表

| 模型 | 原来显示／存储的作者 | 核对结果 | 已落实的调整 |
|---|---|---|---|
| GPT-4o | OpenAI，2024 | 正确；报告明确指定这种引用方式 | 无需修改 |
| Gemini 2.5 Pro | Comanici et al.，2025；存储 3,435 个作者字段 | 文献正确；导入的上游元数据把 11 个姓名拆开 | 按报告首页改为 **Gemini Team**；URL 固定到 v6 |
| Qwen2.5-72B | Qwen，2024 | 正确；2024 是首发年，Qwen 是有依据的团队简称 | 规范为首页署名 **Qwen Team**；URL 固定到 2024 年 v1 |
| Llama 3.1-8B-Instruct | Grattafiori et al.，2024；存储 561 个作者字段 | 文献正确；Grattafiori 对应 v3，两个姓名被元数据拆开 | 按报告首页改为 **Llama Team**；URL 固定到 v3 |
| Qwen3.5-9B | Qwen Team，2026；官方模型卡 | 标题、年份、作者和来源正确 | 链接固定到与实验配置一致的 README 提交，加入 revision 和访问日期 |

**这里不是“四条错引”。** Gemini、Llama 是作者元数据的实际修复；Qwen2.5 是规范化；Qwen3.5 是可追溯性完善。原来的 Comanici／Grattafiori 姓名不是凭空编造的，它们来自 arXiv 的版本化作者记录。

## 3. 逐条详细核对

### 3.1 GPT-4o：原引用正确，保留

引用键：`openai2024gpt4o`。

| 核对项 | 结果与依据 |
|---|---|
| 标题 | **GPT-4o System Card**，与官方 PDF、arXiv 一致 |
| 团体作者 | **OpenAI**；不是根据公司名称自行推定 |
| 年份 | **2024**；报告落款 2024-08-08，arXiv v1 提交 2024-10-25，两者同年 |
| 文献类型 | System card／技术报告；使用 `arXiv preprint` 描述其存档版本成立 |
| arXiv | `2410.21276` |
| DOI | `10.48550/arXiv.2410.21276`，对应同一份 system card |
| 模型匹配 | §1 直接介绍 GPT-4o，涵盖文本输入输出；并非 GPT-4、GPT-4 Turbo 或 GPT-4o mini 的报告 |
| 对应论述 | 支持 §4.4 中 GPT-4o 的模型身份；不用于证明本文的 SA-MCGS 实验收益 |
| 最终处理 | 原 BibTeX 条目逐字保留 |

最关键的一手证据是报告首页脚注：**“Please cite this work as ‘OpenAI (2024)’.”** 所以这里不应因为 arXiv 中存在长篇个人贡献者名单，就强行改成个人首作者形式。

报告发布日期和 arXiv 上传日期不同不构成错误：前者是报告公开日期，后者是预印本入库日期。当前只有年份的作者—年份引用没有混淆这两件事。

核对来源：[官方报告页面](https://openai.com/index/gpt-4o-system-card/)、[官方 PDF 首页及 §1](https://cdn.openai.com/gpt-4o-system-card.pdf)、[arXiv 书目页](https://arxiv.org/abs/2410.21276)、[v1 全文首页](https://arxiv.org/html/2410.21276v1)。

### 3.2 Gemini 2.5 Pro：文献正确，修复上游作者解析问题

引用键：`comanici2025gemini25`。

| 核对项 | 结果与依据 |
|---|---|
| 标题 | **Gemini 2.5: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities** |
| 首页署名 | **Gemini Team**，机构标注为 Google；已对照 HTML 和实际 PDF 首页 |
| 年份 | **2025**；没有因 2026 年访问而改动文献年 |
| 版本 | v1 为 2025-07-07；本次核对 v6 为 2025-12-19 |
| arXiv／DOI | `2507.06261`／`10.48550/arXiv.2507.06261`，均正确 |
| 文献类型 | arXiv technical report；登记类型为 Preprint |
| 模型匹配 | §3.1 Table 2 明确对应 **Gemini 2.5 Pro** 与 API 名 `gemini-2.5-pro` |
| 已落实 | 作者改为 `{{Gemini Team}}`；书目 URL 固定到 `2507.06261v6`；其余事实字段保留 |

#### 作者列表进行了全量比对

原条目包含 **3,435 个 BibTeX 作者字段**，与 arXiv 的 3,435 个 `citation_author` 字段逐项、逐序完全一致。因此问题来自上游机器元数据，不是本地编辑随意加了作者。

但报告正文 §7 有 **3,424 条贡献者姓名**。其中 11 位作者的括号别名触发了解析错误，每人被拆成两个作者字段：

| 元数据拆分结果 | 报告正文的完整姓名 |
|---|---|
| Jerry / Liu | Jerry (Chun-Ting) Liu |
| Xintian / Wu | Xintian (Cindy) Wu |
| Qiong / Hu | Qiong (Q) Hu |
| Chuqiao / Xu | Chuqiao (Joyce) Xu |
| Jilei / Wang | Jilei (Jerry) Wang |
| Katrina / Xu | Katrina (Xinyi) Xu |
| Tony / Nguyên | Tony (Tuấn) Nguyễn |
| Zhixin / Lai | Zhixin (Lucas) Lai |
| Hui / Li | Hui (Elena) Li |
| Warren / Chen | Warren (Weilun) Chen |
| Yuvein / Zhu | Yuvein (Yonghao) Zhu |

此外还核对到撇号字形和个别变音符差异；完整位置与差异保存在证据文件。这里无需猜测数千人的姓名结构：报告本身已经给出集体署名 **Gemini Team**，直接采用它最稳妥。

#### 为什么不能简单手写 “and others”

使用项目原有 `acl_natbib.bst` 做了独立编译检查：原长名单显示前 19 位作者和 **“3416 others”**；改成“三位作者加 `and others`”反而显示 **“1 others”**。后者不能作为修复。现在采用团队署名，实际输出为 **Gemini Team. 2025.**，不必改动 ACL 样式文件。

#### 引用是否支持原句

模型身份有直接依据，尤其 Table 2 区分 Pro、Flash 等型号。官方开发者文档及 2025-06-17 发布说明也确认稳定端点名称。

“proprietary”这个分类与官方资料一致，但这份技术报告没有直接写该词，不能声称已在报告中找到许可证结论。Google 官方 Gemma 模型卡使用了 proprietary Gemini models 的表述，提供额外佐证。当前正文只需正常介绍模型，不需要为了这个常规分类再塞入一条无关模型的引用。

核对来源：[v6 报告](https://arxiv.org/abs/2507.06261v6)、[全文及贡献者名单](https://arxiv.org/html/2507.06261v6)、[模型名与 API 名对应表](https://arxiv.org/html/2507.06261v6#S3.T2)、[DOI 登记](https://api.datacite.org/dois/10.48550/arXiv.2507.06261)、[Google 发布说明](https://developers.googleblog.com/en/gemini-2-5-thinking-model-updates/)、[Google 模型卡中的分类依据](https://ai.google.dev/gemma/docs/core/model_card_4#ethics_and_safety)。

### 3.3 Qwen2.5-72B：2024 年正确，团队名规范化

引用键：`qwen2024qwen25`。

| 核对项 | 结果与依据 |
|---|---|
| 标题 | **Qwen2.5 Technical Report** |
| 首页署名 | v1、v2 均为 **Qwen Team** |
| 首版 | v1：**2024-12-19** |
| 修订版 | v2：**2025-01-03** |
| arXiv／DOI | `2412.15115`／`10.48550/arXiv.2412.15115` |
| 模型匹配 | 报告包含 Qwen2.5 的指令调优模型和 72B 规模；官方模型卡明确为 Qwen2.5-72B-Instruct |
| 出版状态 | 官方记录为 arXiv preprint；没有核实到应替换当前来源的会议／期刊版本 |
| 已落实 | `{{Qwen}}` 规范成 `{{Qwen Team}}`；URL 固定到 2024 年 v1；2024 年不改 |

#### 为什么不把年份机械改成 2025

当前 arXiv 最新版 BibTeX 导出可能给出 2025，对应 v2 的版本年份。**首版是 2024 年**，DataCite 的 publicationYear 和 Qwen 官方 GitHub 推荐引文也支持 2024。原条目的年份不是错误。

为使所引年份与锁定的来源一致，本次选用 v1 URL。没有把 v2 的新作者名单与 v1 年份拼成混合记录。v1 核心作者有 41 人；v2 增加 Tianyi Tang，共 42 人。团队署名在两版首页均有直接依据。

原 `Qwen` 是合理的团体简称，不是虚构作者。改为 `Qwen Team` 是让 BibTeX 更贴近报告首页，并与另一条 Qwen 记录一致。另外，arXiv 最新导出还存在把冒号拆成独立作者字段的现象，不能完全依赖自动导出。

#### 是否引用了错误的一代模型

没有。Qwen2、Qwen2.5-VL、Qwen2.5-Omni、Qwen2.5-1M 和 Qwen3 的材料不能只凭名字接近替换这条引用。当前 Qwen2.5 技术报告比旧 Qwen2 报告更直接对应正文的 72B 模型。

本地 LEA 部署记录对应官方 Qwen2.5-72B-Instruct 系列。这里保持用户确认的正文模型简称；历史 API 提供方的精确 checkpoint 并不能单靠论文引用来反推，本次不把后来的本地部署版本冒充历史服务端的独立验证结果。

核对来源：[v1 书目页](https://arxiv.org/abs/2412.15115v1)、[v1 首页和贡献者说明](https://arxiv.org/html/2412.15115v1)、[v2 书目页](https://arxiv.org/abs/2412.15115v2)、[DOI 登记](https://api.datacite.org/dois/10.48550/arxiv.2412.15115)、[官方推荐引用](https://github.com/QwenLM/Qwen3#citation)、[官方 72B Instruct 模型卡](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct)。

### 3.4 Llama 3.1-8B-Instruct：版本解释清楚，采用真实团队署名

引用键：`grattafiori2024llama3`。

| 核对项 | 结果与依据 |
|---|---|
| 标题 | **The Llama 3 Herd of Models** |
| 首页署名 | **Llama Team, AI @ Meta**；Meta 官方出版记录也署名 Llama team |
| 年份 | **2024**；报告发布、arXiv 初版及 v3 都在该年 |
| 版本 | v1 为 2024-07-31；v3 为 2024-11-23 |
| arXiv／DOI | `2407.21783`／`10.48550/arXiv.2407.21783` |
| 模型匹配 | Introduction 和 Table 1 明确包括 **Llama 3.1 8B Instruct** |
| 出版状态 | Meta 将 publisher 标为 arXiv；没有核实到正式会议／期刊替代版本 |
| 已落实 | 作者改为 `{{Llama Team}}`；URL 固定到 v3；标题、年份、DOI 保留 |

#### 为什么有的论文写 Dubey，有的写 Grattafiori

v1／v2 的个人作者列表以 **Abhimanyu Dubey** 开头；v3 以 **Aaron Grattafiori** 开头。贡献者分组变化解释了这一差别。因此原 `Grattafiori et al., 2024` 对应 v3，是有依据的引用，不能判为错写首作者。

内部引用键保留 `grattafiori2024llama3` 不影响读者：最终显示的作者由 BibTeX 的 `author` 字段决定。更改内部键只会额外增加漏改风险。

#### 全量作者核对发现了什么

原本地名单的 **561 个姓名字段**与 arXiv v3 自动元数据逐项完全一致。报告正文贡献者列表有 **559 条姓名记录**，其中两个括号别名被拆开：

| 错误的元数据片段 | 正文中的完整姓名 |
|---|---|
| Guangyi / Zhang | Guangyi (Jack) Zhang |
| Yu / Wang | Yu (Sid) Wang |

将这两组恢复为单个人名后，559 条记录与全文名单的顺序完全吻合。

正文名单本身还重复出现 Shaun Lindsay、Shuqiang Zhang，因此 559 条记录对应 557 种姓名字符串。不能把这一点误报为本地新增作者，也不能在没有身份依据时擅自去重。本次采用报告的团队署名，绕开机器拆名问题；另存了保留原始顺序的完整个人名单修复版本，便于追溯。

#### 报告标题为什么是 Llama 3，却可以支持 Llama 3.1

报告正文解释了所讨论的 3.1 代模型，并在 Table 1 明列 8B Instruct。官方模型卡也确认这一型号。标题较短并不意味着引用错代，不需要另外找一篇不存在的“Llama 3.1-8B 专用论文”。

核对来源：[v3 报告及 Table 1](https://arxiv.org/html/2407.21783v3#S1)、[v1 元数据](https://arxiv.org/abs/2407.21783v1)、[v3 元数据](https://arxiv.org/abs/2407.21783v3)、[Meta 官方出版记录](https://ai.meta.com/research/publications/the-llama-3-herd-of-models/)、[DOI 登记](https://api.datacite.org/dois/10.48550/arXiv.2407.21783)、[官方 8B Instruct 模型卡](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)。

### 3.5 Qwen3.5-9B：模型卡可以引用，固定到实际实验版本

引用键：`qwen2026qwen35nine`。

| 核对项 | 结果与依据 |
|---|---|
| 引用对象 | 官方 **Qwen3.5-9B** 模型卡 |
| 作者 | **Qwen Team**，与官方署名及引用建议一致 |
| 年份 | **2026**，正确 |
| 公开发布记录 | 官方 News 在 **2026-03-02** 宣布 9B 等小模型可用 |
| 仓库创建日期 | 2026-02-27；创建日期不等于公开发布日期 |
| 固定提交 | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| 与实验一致性 | 完整 SHA 与本地 `configs/qwen35.json`、部署 manifest 一致 |
| 模式支持 | 固定模型卡明确支持 `enable_thinking=false`；与现有配置一致 |
| 文献类型 | Official model card；没有填入不存在的 DOI、arXiv 编号或会议 |
| 已落实 | 固定 README URL；补记 revision c202236 与访问日期 October 1, 2026 |

#### 为什么不强制换成系列博客或别的技术报告

模型卡推荐引用的系列博客名为 **Qwen3.5: Towards Native Multimodal Agents**，月份为 February 2026。它是系列发布材料，9B 小模型在之后加入。当前句子需要的是特定 9B 模型的出处，直接引用该官方模型卡更具体，也符合引用软件／模型资产的用途。

因此不把“系列博客标题＋9B 模型卡 URL＋系列初发月份”混装成一条书目，也不拿 Qwen3.5-Omni 等不同配置的报告来代替。

固定模型卡和本地配置支持该模型可以进行文本实验，并使用非 thinking 模式。这里没有因此发明 `Qwen3.5-9B-Instruct` 这个额外模型名。现有模型名保持不变。

本次检查了三种方法各一个已有实际请求审计记录，它们均记录关闭 thinking。这是局部执行记录与引用来源的交叉核对，**不是重新逐个审计了全部 240 个结果**。

核对来源：[官方模型卡](https://huggingface.co/Qwen/Qwen3.5-9B)、[固定版本 README](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)、[HF 模型元数据](https://huggingface.co/api/models/Qwen/Qwen3.5-9B)、[提交历史](https://huggingface.co/Qwen/Qwen3.5-9B/commits/main)、[官方发布记录](https://github.com/QwenLM/Qwen3.8#news)。原 Qwen3.5 GitHub 仓库入口目前重定向到 Qwen3.8，但保留对应发布消息；本次引用的 HF 固定链接不依赖这一仓库重命名。

## 4. 引用与正文说法是否匹配

当前引文所在句子的作用，是介绍五个 LLM backbone，区分 proprietary 与 open-weight。五条出处分别附在相应模型名称后面，没有把某一模型论文引用在另一个模型后面，也没有把它们当成 SA-MCGS 结果的外部证据。

| 当前句子的用途 | 核对结论 |
|---|---|
| GPT-4o 的身份 | 官方 system card 支持 |
| Gemini 2.5 Pro 的身份与 Pro 型号 | 技术报告和 Table 2 支持 |
| Qwen2.5-72B 指令模型 | 技术报告与官方模型卡支持 |
| Llama 3.1 8B 指令模型 | 报告 Table 1 与官方模型卡支持 |
| Qwen3.5-9B 的身份 | 特定模型卡直接支持 |
| 开放权重模型分类 | 对应官方模型卡及发布说明支持；正文采用 open-weight，没有扩写为无条件的 open-source |
| 本文自身的比较成绩 | 由论文实验数据支持，不由五篇模型出处证明；当前引用位置没有越界 |
| “五个模型代表全部模型家族或尺度” | 当前句子没有这一说法；本次也没有重新加入此类泛化论断 |

本次不需要在 §4.4 增加解释性或防御性文字。实际正文文字保持原样，只由新的作者字段自动更新括号中的引文。

## 5. 已应用的精确改动

| 条目 | 字段 | 修改前 | 修改后 | 性质 |
|---|---|---|---|---|
| Gemini | `author` | 完整 3,435 字段名单 | `{{Gemini Team}}` | 采用报告真实署名，消除元数据拆名及余下作者计数问题 |
| Gemini | `url` | `/abs/2507.06261` | `/abs/2507.06261v6` | 固定已核对版本 |
| Qwen2.5 | `author` | `{{Qwen}}` | `{{Qwen Team}}` | 署名规范化 |
| Qwen2.5 | `url` | `/abs/2412.15115` | `/abs/2412.15115v1` | 与所引 2024 年初版一致 |
| Llama | `author` | 完整 561 字段名单 | `{{Llama Team}}` | 采用报告真实署名，消除元数据拆名问题 |
| Llama | `url` | `/abs/2407.21783` | `/abs/2407.21783v3` | 固定已核对版本 |
| Qwen3.5 | `url` | 模型仓库入口 | 实验固定提交的 README | 锁定具体来源版本 |
| Qwen3.5 | `note` | 原模型卡说明 | 模型卡类型、revision 与访问日期 | 补全模型资产引用信息 |

所有五个引用键保留，标题和年份保留。已有 DOI 保留；**没有给 DOI 加上 v1／v3／v6 后缀**。

当前 ACL 样式优先让标题链接到 DOI。因此三条 arXiv URL 的版本固定体现在 BibTeX 和本审计记录中，PDF 的 DOI 标题链接仍是规范的、与版本无关的 DOI 入口。Qwen3.5 无 DOI，PDF 标题直接链接到固定 README。这里没有把“BibTeX 中的版本 URL”误说成“PDF 中每个链接都已锁定版本”。

本次四条修改后的参考文献在修订稿中标红，GPT-4o 沿用旧绿色。链接文字保留 ACL 原有链接颜色。原黑字删除记录不受影响。

## 6. 编译与最终检查

| 检查项 | 结果 |
|---|---|
| 五条新增引用键是否各有一条定义 | 通过 |
| 五条引用是否仍与五个模型逐一对应 | 通过；净稿第 6 页 |
| 五条参考文献是否实际出现在新 PDF | 通过；净稿第 10 页 |
| GPT-4o 和原有书目是否保持不变 | 通过；具体逐条结果见独立 QA 文件 |
| 科学正文源文件是否改变 | 未改变；只改 `custom.bib` 和参考文献颜色钩子 |
| ACL bibliography 样式 | 未改 `acl_natbib.bst` |
| 编译 | 净稿和修订稿均成功；无 undefined citation／reference |
| 净稿排版 | 第 6、8、9、10 页已渲染检查，没有新增挤压、遮挡或越栏 |
| 修订稿参考文献 | 第 12、13 页已渲染检查；四条调整正确标红，GPT-4o 保持原颜色 |
| 正文页数 | Conclusion 仍在第 8 页；Limitations 与 References 从第 9 页开始 |
| 全文页数 | 净稿 24 页；修订稿 29 页 |

编译日志中，净稿没有 overfull box。修订稿仍有原已存在的 Introduction 第 89 行 5.21777 pt overfull 提示，属于保留修订文字的排版，不是本次书目修改产生的问题。本次不为此变动正文。

没有为了让审计“显得做了修改”而更换正确年份、虚构正式发表会议、改变模型名称或重写正文结论。

## 7. 当前五条 BibTeX

以下与正式文件一致，便于逐字段核对：

```bibtex
@article{openai2024gpt4o,
    author  = {{OpenAI}},
    title   = {{GPT-4o} System Card},
    journal = {arXiv preprint arXiv:2410.21276},
    year    = {2024},
    doi     = {10.48550/arXiv.2410.21276},
    url     = {https://arxiv.org/abs/2410.21276},
}

@article{comanici2025gemini25,
    author  = {{Gemini Team}},
    title   = {{Gemini 2.5}: Pushing the Frontier with Advanced Reasoning, Multimodality, Long Context, and Next Generation Agentic Capabilities},
    journal = {arXiv preprint arXiv:2507.06261},
    year    = {2025},
    doi     = {10.48550/arXiv.2507.06261},
    url     = {https://arxiv.org/abs/2507.06261v6},
}

@article{qwen2024qwen25,
    author  = {{Qwen Team}},
    title   = {{Qwen2.5} Technical Report},
    journal = {arXiv preprint arXiv:2412.15115},
    year    = {2024},
    doi     = {10.48550/arXiv.2412.15115},
    url     = {https://arxiv.org/abs/2412.15115v1},
}

@article{grattafiori2024llama3,
    author  = {{Llama Team}},
    title   = {The {Llama 3} Herd of Models},
    journal = {arXiv preprint arXiv:2407.21783},
    year    = {2024},
    doi     = {10.48550/arXiv.2407.21783},
    url     = {https://arxiv.org/abs/2407.21783v3},
}

@misc{qwen2026qwen35nine,
    author  = {{Qwen Team}},
    title   = {{Qwen3.5-9B}},
    year    = {2026},
    url     = {https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md},
    note    = {Official model card, revision c202236. Accessed October 1, 2026},
}
```

## 8. 证据与修改文件

全部原始来源快照、作者全量差异、版本记录、编译记录和修改前备份已保存在本报告同目录的 `citation_audit/` 中。子审计报告描述的是“修改前状态与建议”，以本总报告第 5／7 节和正式 BibTeX 为实际落实结果。

- [新增范围与引用上下文](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/scope.json)
- [GPT-4o 来源快照记录](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/gpt4o/sources.json)
- [Gemini 完整子审计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/gemini/audit.md)
- [Gemini 全量作者差异](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/gemini/metadata_vs_fulltext_differences.json)
- [Llama 完整子审计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/llama/audit.md)
- [Llama 修复后的完整个人名单备选](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/llama/corrected_full_entry_v3.bib)
- [两条 Qwen 完整子审计](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/qwen/audit.md)
- [实际 PDF 引用链接与分页检查](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/pdf_qa.json)
- [独立最终 QA](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/independent_final_qa.json)
- [归档文件 SHA-256 清单](/Users/chenlong/WorkSpace/MCGS_Law/2026NAACL/SA-MCGS/manuscript_revision_20261001/citation_audit/manifest_sha256.json)
- [正式参考文献源文件](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/custom.bib:446)
- [正文中五条引用的位置](/Users/chenlong/WorkSpace/MCGS_Law/paper/latex/acl_latex.tex:324)

正式发表状态的检查覆盖报告页面、提供方页面、DOI 登记和精确标题检索；没有发现应该替换当前技术报告／模型卡的正式出版版本。这是本次核对结果，不把“没有查到”写成对所有可能出版渠道的绝对断言。
