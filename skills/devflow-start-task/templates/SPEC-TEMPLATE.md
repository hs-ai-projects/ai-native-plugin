# SPEC: <task-id> <一句话标题>

## 0. 不可违反原则
<列出这个任务不能碰的边界；引用当前仓库 CLAUDE.md 的核心规则，不重复抄写>

### Decision（Skill 维护）
status: accepted   # accepted | deferred | rejected
actor: <决策人>
timestamp: <YYYY-MM-DDTHH:MM:SSZ>

## 1. Requirement（需求理解）
- 背景 / 目的（从 intent.md 提炼，不脱离 intent 重新理解需求；首行引用 intent.md 路径）
- 影响范围（涉及哪些 repo / 模块）
- 安全与边界（不做什么）
- 假设清单（需求信息不全时列出）

## 2. Acceptance Criteria（验收标准）
- AC-01: <可验证的单条标准>
- AC-02: ...
（每条 AC 需能映射到 verification.json 里的某个 test case）

## 3. Task Breakdown（任务拆分）
- Task-1 [owner: frontend] 描述 / 依赖: 无
- Task-2 [owner: backend] 描述 / 依赖: 无
（标注串并行关系，供编排读取）

## 4. Status（Skill 维护，运行时更新）
- 当前阶段 / 各 Task 状态 / 最近一次 verification 结果链接 / 最近一次埋点 event_id
