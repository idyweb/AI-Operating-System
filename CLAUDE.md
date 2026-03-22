# Second Brain — Personal AI Operating System

## Mission
Build a production-grade personal AI platform that acts as a "second me".
Goal: $50,000 this year through AI Engineer role (FMCG) + Backend Dev contract (startup).

## Stack
- Python 3.12 + uv (package manager)
- FastAPI (API layer) — root main.py is the entrypoint
- Celery + Redis (async task queue)
- Postgres + pgvector (database + vector search)
- Anthropic Claude (sole LLM provider)
- Langfuse cloud v4 (observability)
- Docker + compose.yml (local dev)

## Architecture — 3 Layers (Dave Ebbelaar pattern)
- Layer 1: Webhook/API triggers → FastAPI → Celery
- Layer 2: Scheduled workflows → Celery Beat
- Layer 3: AI Agent workflows → Workflow/Node engine

## Core Abstractions (read these first)
- `core/config.py` — Settings via pydantic-settings, all env vars
- `core/context.py` — TaskContext (immutable state) + MissionContext
- `core/nodes.py` — BaseNode, AgentNode, RouterNode, TransformNode
- `core/workflow.py` — Workflow orchestrator with Langfuse tracing
- `workflows/registry.py` — Register workflows with @register decorator
- `workers/celery_app.py` — Celery factory + run_async helper
- `workers/tasks.py` — Generic run_workflow task

  # uv — source of truth for version
├── api/
│   ├── main.py          # FastAPI factory + lifespan
│   └── routers/
│       ├── health.py    # /health + /health/ready
│       └── workflows.py # /workflows/run, /workflows, /workflows/status
├── core/
│   ├── config.py        # Settings
│   ├── context.py       # TaskContext + MissionContext
│   ├── nodes.py         # BaseNode, AgentNode, RouterNode, TransformNode
│   └── workflow.py      # Workflow base c│   └── workflow.py      # Wo�� celery_app.py    # Celery factory
│   └── tasks.py        # run_workflow t│   └── tasks.py        # run_workflow t�.py     # @register decorator + get_workflow()
├── db/
│   └── base_model.py   # Async SQLAlchemy base with CRUD
└── skills/             # Reusable agent skills (coming next)
```

## What's Been Built
- [x] Core engine (TaskContext, BaseNode, Workflow)
- [x] Celery + task registry
- [x] FastAPI with health + workflow endpoints
- [x] Dynamic versioning from pyproject.toml
- [x] Langfuse v4 integration (graceful degradation)
- [ ] DB models + Alembic migrations
- [ ] First real workflow (to be decided)
- [ ] compose.yml tested end-to-end
- [ ] GitHub push

## Session Notes
Load ~/.claude/agents/ai-engineer.md and ~/.claude/agents/agent-designer.md
for all AI workflow work. Load ~/.claude/agents/devops-reviewer.md for
Docker/infra work.
