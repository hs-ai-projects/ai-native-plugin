# 开发工作流规范

本仓库开发统一走 test 分支的 worktree 隔离流程，不直接改动 main 工作区。

## 步骤

1. 开发前，从 test 分支拉一个独立 worktree：

   ```bash
   git fetch origin
   git worktree add -b BRANCH_NAME WORKTREE_PATH origin/test
   ```

2. 全部改动在该 worktree 内完成——编码、验证、测试都在 worktree 里，不碰
   main 工作区。
3. 完成后，把 worktree 的分支提 MR 到 test：

   ```bash
   glab mr create --source-branch BRANCH_NAME --target-branch test --title "..." --yes
   ```

4. MR 合入 test 之前，main 工作区保持只读基线，不落任何改动。
