# Spec: <名称>

> 用途：定义「什么叫正确」，不定义「代码怎么写」。
> 只保留防止实现 Agent 猜测所需的锚点，不要堆砌篇幅。
> 不适用的小节直接写「无」或删除。

## 现状与目标
- **Current Behavior**（现状）：……
- **Expected Behavior**（目标行为）：……

## 范围
- In scope：……
- Out of scope：……

## 功能规则（FR）
- FR-01：……

## 验收标准（AC；Given / When / Then，可测试）
- AC-01：Given …… When …… Then ……
- AC-02：（含边界：空 / 非法 / 幂等 / 并发）

## 契约（Contract）
> 前后端或外部依赖共用的契约必须在此固定，禁止实现方各自猜测。
> 无契约变化时写「无」。

- 接口 / 数据 / 状态 / 权限：……
- Error Code → 前端行为：……

## 前端 / 后端行为（FULL_STACK 或涉及可观察行为时必填，否则删）
- Frontend Behavior：……
- Backend Behavior：……

## 影响与回滚
- 数据影响 / 兼容性 / 安全：……（无则写「无」）
- 影响文件（粗列）/ 回滚：……

## Open Questions
- 无
