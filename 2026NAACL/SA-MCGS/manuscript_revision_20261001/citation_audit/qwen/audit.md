# Qwen 新增引用审计

审计日期：2026-10-01。范围：`qwen2024qwen25`、`qwen2026qwen35nine`；只读核对，未修改论文、BibTeX 或实验记录。

**结论：两条引用均指向真实、相关、可访问的官方来源，未发现必须据此判定为错引的事实问题。** Qwen2.5 的 2024 年份有首版与官方推荐引文的双重支持，团队署名也有报告首页支持。Qwen3.5-9B 的 2026 年份、模型名称与官方仓库均准确，且已有可与实验配置对上的固定提交。建议仅做两类最小完善：将 Qwen2.5 的团队名称统一为首页上的 `Qwen Team`；为 Qwen3.5 模型卡固定版本并注明访问日期。两项属于规范化和可复核性增强，不应报告为发现两条假引用或硬性书目错误。

## 1. 本地引用及引用语境

| 条目 | 本地位置 | 当前关键字段 | 判定 |
|---|---|---|---|
| `qwen2024qwen25` | `paper/latex/custom.bib:465–472` | Qwen；Qwen2.5 Technical Report；arXiv:2412.15115；2024；10.48550/arXiv.2412.15115 | 标题、编号、DOI、URL 正确；2024 有官方依据；团队作者可规范成 Qwen Team |
| `qwen2026qwen35nine` | `paper/latex/custom.bib:483–489` | Qwen Team；Qwen3.5-9B；2026；官方 HF 模型卡 | 正确引用特定模型卡；不必强制换成系列博客 |

引用出现在 `paper/latex/acl_latex.tex:324`，§4.4 的新文本把 Qwen2.5-72B、Qwen3.5-9B 列为 open-weight backbones。`paper/latex/revision_experiments.tex:30` 另声明 Qwen3.5-9B 使用 `enable_thinking=false`。

两个外部来源支持模型身份及开放权重属性。它们不证明作者自己的实验确实使用了某模型，也不支持本文方法的性能优势；后两项须由本地实验记录和结果支撑。该处没有借模型论文引文外推新的性能结论，未发现引用与句意不匹配。

## 2. Qwen2.5：年份、团队署名、作者名单与版本

### 可确定的书目信息

- 准确标题：**Qwen2.5 Technical Report**。
- arXiv：**2412.15115**；类别 `cs.CL`；DOI：**10.48550/arXiv.2412.15115**。
- v1 提交：**2024-12-19 17:56:09 UTC**；v2 提交：**2025-01-03 02:18:21 UTC**。
- v1 与 v2 的正文首页署名均为 **Qwen Team**；§7 再列 Core Contributors 与 Contributors。
- v1 核心作者名单含 41 人，以 An Yang 开始；v2 增加 Tianyi Tang，共 42 人。完整、按顺序提取的名单保存在 `evidence.json`。
- 目前 arXiv 页面未列正式期刊/会议出版信息；DataCite 的资源类型为 Preprint，publicationYear 为 2024，relatedIdentifiers 为空。

一手证据：[v1 书目页](https://arxiv.org/abs/2412.15115v1)、[v2 书目页](https://arxiv.org/abs/2412.15115v2)、[v1 首页与 §7](https://arxiv.org/html/2412.15115v1)、[v2 首页与 §7](https://arxiv.org/html/2412.15115v2)、[DataCite 登记](https://api.datacite.org/dois/10.48550/arxiv.2412.15115)。

### 为什么 2024 不能直接判错

官方 [Qwen GitHub Citation](https://github.com/QwenLM/Qwen3#citation) 仍推荐 `An Yang … Zihan Qiu` 的 v1 名单与 `year={2024}`。原 `QwenLM/Qwen2.5` 仓库 URL 已重定向到 Qwen3，README 仍明确保留 Qwen2.5 引文。登记方也采用首发年 2024。

当前 [arXiv BibTeX 导出](https://arxiv.org/bibtex/2412.15115) 使用 2025，反映其最新 v2 的版本年；这与首发年惯例不同，不构成 2024 错误。导出还把作者显示中的冒号拆成了独立 `and : and`，不应盲目原样复制。若另行选择“精确引用 v2”的规范，2025 可用，但应明确 v2，不能只为与导出一致而声称 2024 是事实错误。

### 为什么团队署名不能直接判错

`author={{Qwen}}` 与 arXiv 书目页的组名前缀一致，而正文首页明确使用 `Qwen Team`。因此这是有来源依据的团体署名，并非把不存在的组织虚构成作者。采用集体署名时，`{{Qwen Team}}` 比 `{{Qwen}}` 更贴近正文首页，也与 Qwen3.5 条目统一。若论文全库采用个人作者，官方推荐的 v1 41 人名单亦可使用；这属于署名策略，不必在当前局部审计中强制展开全部个人作者。

### 所支持的模型

报告直接讨论 Qwen2.5 的 base、instruction-tuned 及量化权重，明确包含 **Qwen2.5-72B-Instruct**。官方 [72B Instruct 模型卡](https://huggingface.co/Qwen/Qwen2.5-72B-Instruct) 与该名字一致。该卡目前还保留发布博客与 Qwen2 报告的旧引文建议；这不意味着较新的 Qwen2.5 技术报告不适合引用。报告本身比旧 Qwen2 报告更直接。

`Qwen2.5-72B` 可以作为表格/正文的简写；本次任务不改变论文模型标签。内部记录确有 `Qwen/Qwen2.5-72B-Instruct-AWQ` 的部署来源，见第 5 节；该事实不要求把量化后缀加入论文，也不能把历史 API 权重版本与后来本地部署版本等同。

## 3. Qwen3.5-9B：确切模型、日期与固定版本

| 字段 | 核实结果 |
|---|---|
| 官方模型仓库 | `Qwen/Qwen3.5-9B` |
| 卡片标题 | `Qwen3.5-9B` |
| 归属 | Qwen；官方引用建议作者为 Qwen Team |
| 模型性质 | post-trained 模型；具有 vision encoder 的 causal language model；可使用文本输入 |
| 公开发布消息日期 | **2026-03-02**，官方 GitHub News 同时宣布 9B、4B、2B、0.8B 可用 |
| HF 仓库创建日期 | 2026-02-27 12:58:26 UTC，不能把“仓库创建”误当成“公开发布日期” |
| 当前/实验固定提交 | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` |
| 该提交日期 | 2026-03-02 00:51:43 UTC，提交消息为更新 README |
| 年份 | **2026** 正确 |
| 许可证元数据 | Apache-2.0；公开权重仓库 |
| 独立 9B 专用论文/DOI | 本次一手检索未发现；不得编造 arXiv 编号或期刊 |

证据：[官方模型卡](https://huggingface.co/Qwen/Qwen3.5-9B)、[固定 README](https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md)、[HF API 元数据](https://huggingface.co/api/models/Qwen/Qwen3.5-9B)、[提交历史](https://huggingface.co/Qwen/Qwen3.5-9B/commits/main)、[官方 GitHub News](https://github.com/QwenLM/Qwen3.8#news)。原 `QwenLM/Qwen3.5` URL 已重定向到 Qwen3.8，但仍保留 2026-03-02 的 Qwen3.5 小模型发布记录；不要把现行仓库标题误写成 Qwen3.5 的文献标题。

`qwen35_hf_readme.md` 与 `qwen35_pinned_readme.md` 下载内容逐字节相同。固定提交 URL 既能定位模型卡，又恰好与本地实验配置一致，适合作为模型卡条目的稳定 URL。

### 官方推荐的是系列博客，但当前模型卡引用仍成立

固定模型卡的 Citation 段推荐：Qwen Team，**Qwen3.5: Towards Native Multimodal Agents**，February 2026，`https://qwen.ai/blog?id=qwen3.5`。这是系列发布博客，不是标题为 Qwen3.5-9B 的技术报告。其月份与 9B 模型的 3 月发布日期不同是正常现象：该系列最初发布的是 397B-A17B，9B 随后加入。

直接引用具体模型卡是有效的来源选择，尤其当前句子只需要识别 9B 模型。无需强制把当前条目替换为较宽泛的系列博客，也不要把博客标题、模型卡 URL、2 月月份混装成一个看似精确的 9B 发布记录。

Qwen 官方博客的无参数/locale 页面在本次直接读取中只返回动态页面壳；搜索索引可取到官方页面内容，显示 2026/02/15，而官方 GitHub News 写 2026-02-16。这个日级差异与当前只有年份的模型卡引文无关，本次不为系列博客武断选择某个日数。官方推荐引文本身只给 February 2026，可安全采用。

### 非 thinking 模式

固定模型卡有 “Instruct (or Non-Thinking) Mode” 段，支持 `chat_template_kwargs={"enable_thinking": false}`。因此同一官方模型可以在非 thinking 模式下运行；无需发明 `Qwen3.5-9B-Instruct` 或把“non-thinking”当作另一个权重模型名。模型卡说明与论文声明一致。

## 4. 正式发表状态与检索边界

核查了 arXiv 当前/版本页、DataCite DOI 元数据、官方 Qwen GitHub 引文段、官方模型卡、Qwen 发布博客，以及精确标题的 Crossref 与 arXiv/ACL Anthology/OpenReview 定向检索。未找到 **Qwen2.5 Technical Report** 的正式会议/期刊替代出版物，也未找到 **Qwen3.5-9B** 对应的独立正式论文。稳妥状态分别为“arXiv technical report/preprint”和“official model card”。这是一项截至审计日的检索结论，不是对所有未来或未索引出版物不存在的证明。

搜索命中 **Qwen3.5-Omni Technical Report**, arXiv:2604.15804，属于不同模型系列/模态配置，不能替代 9B 卡片。Qwen2.5-VL、Qwen2.5-Omni、Qwen2.5-1M 和 Qwen3 报告也不能仅凭相似名称替换当前来源。正式发表检索返回的许多 ACL/ICLR 论文仅在参考文献中引用 Qwen2.5，不能据此声称 Qwen2.5 报告自己发表于 ACL/ICLR。

原始登记结果和所有成功下载的官方页面快照均在本目录；`source_downloads.json` 记录 URL、响应路径、文件大小与失败项，`evidence.json` 给出可机读结论、搜索范围和本地依据。

## 5. 内部模型对应核查（不改变正文显示名）

### Qwen3.5

- `2026NAACL/SA-MCGS/experiments/kimi_qwen35_three_methods_20260924/configs/qwen35.json:4–14`：官方仓库、上述完整 SHA、BF16、无量化、131072 部署上下文、`enable_thinking=false`。
- `deployment_audit/qwen_manifest.json:2–7`：2026-09-24 抓取的同一仓库与 SHA。
- `actual_request_audit.json`：已观察 One-shot、LEA、SA-MCGS 各一个实际请求，三者均记载关闭 thinking；这是对三种方法样本的核对，不冒充本次重新检查了全部 240 个输出。
- `qwen35_completion_receipt.json`：已有完成及审计收据；本次引用审计不重新执行模型推理。

### Qwen2.5

`2026NAACL/SA-MCGS/experiments/lea_full320_completion_20260923/cluster_qwen72b/official_model_metadata.json` 记录官方 AWQ 仓库，SHA 为 `698703eae6604af048a3d2f509995dc302088217`，base model 是 Qwen2.5-72B-Instruct。对应 `historical_provider_confirmation.json` 说明历史服务来源是用户转述的 XHub 人员确认，并明确未提供历史精确权重版本及服务默认参数；不得把它抬高为独立验证了历史 provider 的完整部署。该文件也明确记录用户不希望在论文显示名加入量化后缀，本次遵守这一范围。

## 6. 可选最小修订（供主审整合，未实际应用）

Qwen2.5 只将团体名规范化；保持首发年、现有键和来源：

```bibtex
@article{qwen2024qwen25,
    author  = {{Qwen Team}},
    title   = {{Qwen2.5} Technical Report},
    journal = {arXiv preprint arXiv:2412.15115},
    year    = {2024},
    doi     = {10.48550/arXiv.2412.15115},
    url     = {https://arxiv.org/abs/2412.15115},
}
```

Qwen3.5 保持模型卡作为引用对象；固定 URL，补访问日期：

```bibtex
@misc{qwen2026qwen35nine,
    author       = {{Qwen Team}},
    title        = {{Qwen3.5-9B}},
    year         = {2026},
    howpublished = {Hugging Face model card},
    url          = {https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md},
    note         = {Revision c202236; accessed 2026-10-01},
}
```

若希望保持主模型入口 URL，可维持原 URL 并在 note 中记录完整 revision。`urldate` 是否打印取决于 BibTeX 样式，故访问日期置于 note 比只加 `urldate` 更稳妥。版本锁定与访问日期不是原条目“真假”的判定条件。
