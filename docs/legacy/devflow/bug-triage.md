# BUG 复杂度判定：FAST_BUG / STANDARD_BUG

DISCOVER 阶段判定 Root Cause 后，紧接着判定复杂度。**不凭感觉拍板**——
派一个 Explore（或 general-purpose）agent 去代码库调研，据调研结论判定。

## 判定维度

派出的 agent 需要回答：

- Root Cause 是否已确认（不是猜测）？
- 影响面涉及几个模块？
- 是否跨前后端联动？
- 回归风险高不高（改动是否牵连既有行为）？

## 判定结果

- **Root Cause 明确、影响面小、低回归** → `FAST_BUG`
- **Root Cause 不明、多模块、前后端联动、高回归** → `STANDARD_BUG`

## 对应产物（判定结果如何影响后续流程）

- `FAST_BUG` → 不建任何文档，DISCOVER 判完直接进 `IMPLEMENT`。
- `STANDARD_BUG` → 建 Spec + Plan（复用 `skills/devflow/spec.md` /
  `skills/devflow/plan.md` 的产出逻辑，Plan 阶段验证方式按
  `skills/devflow/test-team.md` 的产出逻辑执行），**过 Gate B** 后才进
  `IMPLEMENT`——跟需求类任务共用同一个 Gate，没有特例。
