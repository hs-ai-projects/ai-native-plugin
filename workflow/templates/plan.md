# Plan: <名称>

> 用途：多 Agent 编排的执行方案。Plan 必须能支撑 Task 拆分与委派，
> 不能写成「前端实现 X、后端实现 Y」这种不可独立验收的空话。

## 实现策略
（1-3 句：契约先行？FE / BE 是否可并行及依据？依赖哪条探索结论？）

## Task Graph
（缩进渲染代码块；串行写明原因，并行标注 ∥）

    BE-01 ─┐
            ├─→ TEST-01        # FE-01 ∥ BE-01（契约已在 SPEC 固定）
    FE-01 ─┘

或：

    BE-01 → FE-01 → TEST-01    # 串行原因：FE 依赖 BE 输出

## 任务拆分
（每个独立验收任务一行一张 Task Card；TEST-01 由 test-verifier 验收）

- [ ] `BE-01` Owner=backend-developer：<以动词开头、可独立验收的一句话>（验收 AC-xx；依赖 无）
- [ ] `FE-01` Owner=frontend-developer：<……>（验收 AC-xx；依赖 BE-01）
- [ ] `TEST-01` Owner=test-verifier：回归与验收全部 AC（依赖 上述实现完成）

## Contract Changes
（与上一版契约的差异 / 是否向后兼容 / 影响哪些消费方；无则写「无」）

## 验证方式
（每个实现任务跑哪条命令、看什么结果算过；不写「确保正常」这类空话）

## 风险 / 回滚
（风险点与对应回滚方案）
