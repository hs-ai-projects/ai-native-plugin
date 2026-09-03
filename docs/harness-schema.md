# harness.yaml 规范

> 插件与目标仓库之间的显式合同：仓库声明"测试命令是什么/源码测试路径在哪"，
> 插件承诺"不猜，只按你说的做"。没有这份文件，插件无法知道该跑哪条验证命令，
> 只能停下来问，**不做探测猜测**——猜错比停下问更糟（这是本插件的既定原则，
> 不同于某些工具"看到package.json就跑npm test"的自动探测做法）。

## 为什么需要它

不同团队仓库的测试命令五花八门：有的用 `npm run test`，有的用 `pytest`，
有的前端用 `vitest`、后端用 `pytest tests/`。插件不可能硬编码猜测，只能靠
仓库自己声明一次、插件永久复用。写一次，以后每个任务都读这份声明，不用
每次都问。

## 字段集

```yaml
project:
  stack:
    type: frontend | backend      # 决定加载哪个 persona
paths:
  business_code: ["src/**"]       # 源码路径（glob模式列表）
  test_code: ["test/**", "tests/**"]  # 测试路径
gates:
  fast: [unit]                    # commit前自查跑哪些层
  full: [unit, contract]          # 汇总验证/独立verifier跑哪些层，contract层可选
commands:
  unit: "npm run test:unit"       # 具体命令，按仓库自己的栈填
  contract: "python3 <checker> ."  # 仅命中跨仓库协作任务时使用
```

（`commands.<layer>` 在现有 `verify_runner.py` 实现中对应
`project.stack.<type>_unit_cmd`/`<layer>_cmd` 的历史命名约定，例如
`backend_unit_cmd`/`frontend_unit_cmd`/`contract_cmd`——本文档描述的
`commands.unit` 是概念名，实际字段名以 `verify_runner.py` 的
`layer_command()` 函数为准，见"怎么生效"一节的具体路径。）

## 怎么生效（谁在什么时候读它）

- **栈判定**：两个主入口（`devflow-start-task`/`devflow-fix-bug`）起步第一
  步用YAML解析器读 `project.stack.type`，决定这次Task工具该派给
  `agents/frontend.md` 还是 `agents/backend.md`。
- **测试同步自查**：`skill:verify --self-check`（frontend/backend agent
  commit前调用）用 `paths.business_code`/`paths.test_code` 两个字段做路径
  匹配，判断"改了业务代码有没有同步改测试"，不是瞎猜"这个文件是不是源码"。
- **验证命令执行**：`skill:verify` 三种模式（`--self-check`/`--independent`/
  `--full`）分别读 `gates.fast`/`gates.full` 声明要跑哪些层，再从
  `project.stack` 里取每层对应的实际shell命令字符串，拼进
  `scripts/verify/verify_runner.py`/`fast-verify.sh` 执行。
- **契约检查（可选）**：命中跨仓库协作任务时，`contract`层的命令由
  `scripts/verify/contract_checker.py` 读取，同时该脚本会用
  `paths.business_code` 判断契约端点是否在本仓库代码里被实际引用（字段级
  漂移检测，见spec 7.15）。

## 缺失时的处理

两个主入口首次在某仓库运行且缺失 `harness.yaml` → **停下询问用户是否要
生成向导**，不强行探测猜测项目结构。这条规则的理由：猜测项目类型/测试命令
出错的代价（在错误的路径上跑了一堆本不该跑的命令）远高于停下来问一句的
代价。
