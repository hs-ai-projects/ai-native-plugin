---
name: verify
description: >
  统一的分层验证契约。被 frontend/backend agent（--self-check，commit前自查）
  和 verifier agent（--independent，独立复核不信任前面结论）以及编排 skill
  （--full，步骤6汇总验证）三方共用。不是可执行脚本，是行为契约文档——具体命令
  执行委托给 ${CLAUDE_PLUGIN_ROOT}/scripts/verify/fast-verify.sh 与
  full-verify.sh/verify_runner.py。
---

# Verify Skill

读取当前仓库根目录的 `harness.yaml`（字段定义见 spec 第9节 / 后续
`docs/harness-schema.md`），按调用方指定的模式执行对应验证。

## 模式：`--self-check`（frontend/backend agent commit 前调用）

1. **测试同步检查**：`git diff --name-only` 对比改动文件列表。若命中
   `harness.yaml` 的 `paths.business_code` 声明的路径，但**没有**同时命中
   `paths.test_code` 声明的路径 → 判定"改了 business_code 但没同步改
   test_code"，先补测试再继续，不允许跳过。
2. **跑快速验证**：执行 `${CLAUDE_PLUGIN_ROOT}/scripts/verify/fast-verify.sh
   <repo_dir>`（只跑 `harness.yaml` 的 `gates.fast` 声明的层，通常是 `unit`）。
3. **FAIL 禁止 commit**：步骤1或步骤2任一为 FAIL，必须先修完再提交，不允许
   带着 FAIL 结果 commit。

## 模式：`--independent`（verifier agent 调用）

**核心原则：不信任 frontend/backend 自查阶段产出的任何文字结论**，只允许使用
以下三类原始数据源重新独立判断：

1. 自己执行 `git diff <base>...HEAD`，自己读改动内容（不接受 agent 转述的
   "改了什么"的文字总结）。
2. **忽略已有的 `.ai-devflow/verification.json`**（哪怕它已经是 PASS），强制
   重新执行 `${CLAUDE_PLUGIN_ROOT}/scripts/verify/full-verify.sh <repo_dir>`
   （跑 `gates.full` 全部层），把新结果作为唯一依据。
3. 自己读 SPEC.md 第2章 Acceptance Criteria 里 owner 对应的 AC 列表，逐条
   核对 diff 是否实际覆盖到，不接受"AC都做完了"这种概括性陈述。

**输出**：只输出 `PASS` 或 `FAIL + EVIDENCE`（EVIDENCE = 具体哪条AC没被diff
覆盖 / 哪一层验证命令失败的原始输出）。**不给修复建议**——verifier 的职责是
判断，不是修复，给出修复建议会让它越权变成"第二个开发者"，模糊了独立判断的
边界。

## 模式：`--full`（编排 skill 汇总验证步骤调用）

执行内容同 `--independent` 的第2点（强制重跑 `full-verify.sh`），但产出直接
写入 `.ai-devflow/verification.json` 供 `scripts/state/attribute.py` 读取归因，
不额外产出 EVIDENCE 摘要（那是 verifier 模式专属的呈现格式）。

## 已知边界

本 skill 不新增验证命令本身——`harness.yaml` 里每一层实际执行什么 shell
命令，仍由目标仓库自己声明（见 harness.yaml 规范文档）。三种模式的区别只在
"读哪些数据源做判断"和"要不要允许基于已有结果短路"，不在"跑什么命令"。
