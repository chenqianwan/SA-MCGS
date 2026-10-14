# 合成测试数据声明

本目录中的所有 `SYN-*`、`syn-*` 记录均为人工构造的接口测试数据，仅用于验证 schema、分层、IAA、裁决冻结、cleanliness 和 clustered bootstrap 代码路径。

- 不来自任何真实合同、披露、法规或专家。
- 标签没有事实含义，不得用作论文数字、案例或定性结论。
- 小型 fixture 通过顶层 `synthetic_fixture: true` 明确放宽正式的 18/24/12 数量门禁；正式输入没有该标记时，脚本强制精确数量。
- `synthetic_system_outputs.template.json` 的 label hash 是占位符；测试会在临时目录中绑定刚生成的合成 freeze hash，不改写本 fixture。

