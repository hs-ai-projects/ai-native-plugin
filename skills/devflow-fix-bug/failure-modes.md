# devflow-fix-bug Failure Modes

| ID | 阶段 | 触发条件 | 兜底行为 | 阻断 |
|----|------|---------|---------|------|
| F01 | 步骤1 | 描述过短且无截图/复现步骤 | AskUserQuestion补问，等待用户输入 | 暂停 |
| F02 | 步骤2 | 目标仓库未配置观测云（owl不在PATH或未声明workspace） | 跳过日志辅助，纯代码grep定位，不报错不阻塞 | 否 |
| F03 | 步骤2 | owl查询返回no_data/error/not_configured | log_summary=null，静默跳过，不展示给用户 | 否 |
| F04 | 步骤2 | severity判定为高风险 | 只输出排查报告，到此止步，不进入步骤3-5 | 是 |
| F05 | 步骤4 | frontend/backend agent自查FAIL | 修完再提交，不允许带FAIL结果commit | 暂停 |
| F06 | 步骤5 | skill:review判verdict=FAIL | 回归归因回流，不直接建MR | 否 |

## 非阻断失败的处理原则

F02/F03：静默跳过，只在内部log行记录原因，不打扰用户看到一堆"未配置"提示。
F06：不是本skill的终态失败，是正常流程分支（回归修复循环）。
