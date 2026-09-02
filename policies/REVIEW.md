# Review Policy

AI Review 分级标准。`ai-review.sh` 会读取本文件的 `- [ ]` 清单拼进 review.md，
同时产出机读 `review.json`（verdict/critical/important/nits/spec_compliance）。

## Critical
- [ ] 改动范围超出 SPEC Task 声明的文件
- [ ] AC 未被任何测试覆盖

## Important
- [ ] business_code 改了但 test_code 没同步改
- [ ] verification.json 存在 NOT_RUN 但被当 PASS 处理

## Nit
- [ ] 命名 / 可读性

Maximum Nit Comments: 5

## 不需要报告
生成文件；CI 已强制的内容（lint/format）。
