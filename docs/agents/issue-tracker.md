# Issue 追踪：GitHub

本仓库的 issue 和 PRD 以 GitHub issue 的形式存在。所有操作使用 `gh` CLI。

注意：本仓库有两个 remote，`gh` 会自动解析到 `github` remote（yds123-div/fpai），因为 `origin`（106.55.151.240:8199/hjjk/fpai）不是 GitHub 主机。

## 操作约定

- **创建 issue**：`gh issue create --title "..." --body "..."`。多行正文使用 heredoc。
- **读取 issue**：`gh issue view <编号> --comments`，可用 `jq` 过滤评论并同时获取标签。
- **列出 issue**：`gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'`，按需加 `--label` 和 `--state` 过滤。
- **评论 issue**：`gh issue comment <编号> --body "..."`
- **添加 / 移除标签**：`gh issue edit <编号> --add-label "..."` / `--remove-label "..."`
- **关闭**：`gh issue close <编号> --comment "..."`

仓库信息从 `git remote -v` 推断——在克隆仓库内运行时 `gh` 会自动完成。

## PR 作为 triage 入口

**PR 作为请求入口：否。**（如果本仓库把外部 PR 当作功能请求处理，则设为 `yes`；`/triage` 会读取此标志。）

设为 `yes` 时，PR 走与 issue 相同的标签和状态流程，使用对应的 `gh pr` 命令：

- **读取 PR**：`gh pr view <编号> --comments`，diff 用 `gh pr diff <编号>`。
- **列出待 triage 的外部 PR**：`gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments`，然后只保留 `authorAssociation` 为 `CONTRIBUTOR`、`FIRST_TIME_CONTRIBUTOR` 或 `NONE` 的（去掉 `OWNER`/`MEMBER`/`COLLABORATOR`）。
- **评论 / 打标签 / 关闭**：`gh pr comment`、`gh pr edit --add-label`/`--remove-label`、`gh pr close`。

GitHub 的 issue 和 PR 共用一套编号空间，所以单独的 `#42` 可能是任意一种——先用 `gh pr view 42` 解析，失败再退回 `gh issue view 42`。

## 当 skill 说「发布到 issue 追踪器」时

创建一个 GitHub issue。

## 当 skill 说「获取相关工单」时

运行 `gh issue view <编号> --comments`。

## 寻路操作（Wayfinding）

供 `/wayfinder` 使用。**map（地图）** 是一个单独的 issue，其**子工单**为各 ticket。

- **Map**：一个带 `wayfinder:map` 标签的 issue，正文存放 Notes / Decisions-so-far / Fog。用 `gh issue create --label wayfinder:map` 创建。
- **子工单**：通过 GitHub sub-issue 关联到 map 的 issue（在 sub-issues endpoint 上用 `gh api`）。如果 sub-issue 功能不可用，把子工单加进 map 正文的任务列表，并在子工单正文顶部写上 `Part of #<map>`。标签：`wayfinder:<类型>`（`research`/`prototype`/`grilling`/`task`）。认领后，工单指派给推进的开发者。
- **阻塞关系**：GitHub **原生 issue 依赖**——权威的、UI 可见的表示方式。添加边：`gh api --method POST repos/<owner>/<repo>/issues/<子工单>/dependencies/blocked_by -F issue_id=<阻塞方数据库id>`，其中 `<阻塞方数据库id>` 是阻塞方的数字 **database id**（用 `gh api repos/<owner>/<repo>/issues/<n> --jq .id` 获取，*不是* `#编号` 或 `node_id`）。GitHub 会报告 `issue_dependencies_summary.blocked_by`（仅未关闭的阻塞方——这是实时的门禁）。如果依赖功能不可用，退回到在子工单正文顶部写一行 `Blocked by: #<n>, #<n>`。当所有阻塞方都关闭时，工单即为解除阻塞。
- **边界查询（Frontier query）**：列出 map 的未关闭子工单（`gh issue list --state open`，限定在 map 的 sub-issue / 任务列表范围内），去掉有未关闭阻塞方（`issue_dependencies_summary.blocked_by > 0`，或 `Blocked by` 行中有未关闭 issue）或已有指派人的；按 map 中顺序取第一个。
- **认领**：`gh issue edit <n> --add-assignee @me`——会话的第一次写操作。
- **解决**：`gh issue comment <n> --body "<答案>"`，然后 `gh issue close <n>`，再把上下文指针（gist + 链接）追加到 map 的 Decisions-so-far。
