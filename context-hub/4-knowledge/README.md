# Knowledge Base — Reference

## AI Engineering
- Agentic patterns: Planning, Reflection, Tool Use, Multi-Agent
- RAG: chunk → embed → retrieve → generate
- Eval-driven development: measure before you optimize

## FastAPI Patterns
- Factory pattern for app creation
- Lifespan for startup/shutdown
- Thin routers — all logic in services

## Celery Patterns
- task_acks_late=True — never lose a job
- worker_prefetch_multiplier=1 — fair dispatch
- Beat for scheduled workflows

## Money Rules
- Always INTEGER for money (kobo/cents)
- Never FLOAT
- Idempotency keys on all financial endpoints