---
name: review
description: >
  代码评审能力。两种触发方式：(1) 被 devflow-start-task/devflow-fix-bug
  内部自动调用（开发完成、验证通过后，建MR前）；(2) 用户直接说"帮我review一下
  这个MR"/"review一下这次改动"时手动单独触发，用于人工评论回修场景的重新评审。
---

# Review Skill

生成 AI Review 包并判断 verdict。内部委托给
`${CLAUDE_PLUGIN_ROOT}/scripts/review/ai-review.sh <sandbox_path> <task_id>`，
本 skill 只描述何时调用、调用后怎么读结果。

## 内部调用（被两条主流程自动触发）

调用时机：`skill:verify` 汇总验证已 PASS，准备建 MR 之前。

```bash
${CLAUDE_PLUGIN_ROOT}/scripts/review/ai-review.sh <sandbox_path> <task_id>
```

脚本产出 `.ai-devflow/<task_id>/review.md`（人读，含diff/AC清单/verification摘要/
policies/REVIEW.md动态清单）与 `review.json`（机读，初始 `verdict: PENDING`）。

**verdict 判断**：基于 `review.md` 的检查清单逐项评估这次改动，把 `review.json`
的 `verdict` 改写为 `PASS` 或 `FAIL`：
- 命中 Critical 级问题（改动范围超出SPEC声明的文件 / AC未被任何测试覆盖）→ `FAIL`
- 命中 Important 级问题（business_code改了test_code没同步 / verification.json有
  NOT_RUN被当PASS处理）→ `FAIL`
- 只有 Nit 级问题（命名/可读性，且不超过 `policies/REVIEW.md` 声明的
  `Maximum Nit Comments`）→ `PASS`，Nit 记录进 `review.json.nits` 供人工MR描述参考
- `FAIL` → 调用方（编排skill）回归归因回流；`PASS` → 调用方继续建MR

## 手动触发（用户直接喊"帮我review一下这个MR"）

适用场景：MR已建好，人工在GitLab上评论过，想让AI重新评审一次当前diff（而非从头
走完整devflow流程）。

1. 确认用户给的是哪个 `task_id`/`sandbox_path`（缺失时问用户，不猜）
2. 同样调用 `ai-review.sh <sandbox_path> <task_id>`，覆盖写入新的 `review.md`/`review.json`
3. 输出 verdict 判断结果给用户看，不自动执行后续建MR/merge动作——手动触发场景下
   由用户自己决定下一步（这跟内部调用不同：内部调用verdict=PASS会自动推进到建MR，
   手动触发只汇报结果，不代替用户做决定）
