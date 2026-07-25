# TASK

Fix issue {{TASK_ID}}: {{ISSUE_TITLE}}

Pull in the issue using `gh issue view <ID>`. If it has a parent PRD, pull that in too.

Only work on the issue specified.

Work on branch {{BRANCH}}. Make commits and run tests.

# CONTEXT

Here are the last 10 commits:

<recent-commits>

!`git log -n 10 --format="%H%n%ad%n%B---" --date=short`

</recent-commits>

# PROJECT BACKGROUND

This is **fpai** - 金融产品智能问答与辅助决策系统.

- **Backend** (`backend/`, Python): FastAPI + AgentScope. Main chain: `backend/orchestrator/run.py` -> `backend/agents/fund_agent_framework.py` (`CoordinatorAgent.plan` outputs plan JSON `{multi, tasks:[{type, question}], final_instruction}`, routes by `type` to business agents). Plan output validation retry loop per ADR-0001 (`backend/agents/plan_validation.py`).
- **Frontend** (`frontend/`): Vue 3 + Vite + Ant Design Vue.
- **Python deps**: managed by `uv` (`backend/pyproject.toml`). `uv sync --all-extras` already ran in sandbox setup, so `.venv` is ready.
- **Tests**: pytest. Run from `backend/`. Integration tests (need MySQL/Redis/MinIO) are marked `integration` - **skip them** in the sandbox (no infra running).

# EXPLORATION

Explore the repo and fill your context window with relevant information that will allow you to complete the task.

Pay extra attention to test files that touch the relevant parts of the code, especially `backend/agents/plan_validation.py` and `backend/tests/test_plan_validation.py` (ADR-0001 plan validation).

# EXECUTION

If applicable, use RGR (Red-Green-Refactor) to complete the task:

1. RED: write one test
2. GREEN: write the implementation to pass that test
3. REPEAT until done
4. REFACTOR the code

# FEEDBACK LOOPS

Before committing, run backend tests (skip integration tests that need MySQL/Redis/MinIO):

```bash
cd backend && uv run pytest -m "not integration"
```

If the issue touches frontend, also run `cd frontend && npm run build` to typecheck.

# COMMIT

Make a git commit. The commit message must:

1. Use conventional commits in Chinese (e.g. `feat: ...`, `fix: ...`, `refactor: ...`, `test: ...`, `docs: ...`, `chore: ...`)
2. Reference the issue (e.g. `#{{TASK_ID}}`)
3. Include: task completed, key decisions, files changed, blockers/notes for next iteration

Keep it concise.

# THE ISSUE

If the task is not complete, leave a comment on the issue with what was done.

Do not close the issue - this will be done later.

Once complete, output <promise>COMPLETE</promise>.

# FINAL RULES

ONLY WORK ON A SINGLE TASK.
