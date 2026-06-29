# Self-hosted Langfuse (Tier-2 trace UI)

Local LLM observability for Policy Copilot, self-hosted via **Podman** so traces
stay on your machine. Optional — the JSONL trace (`data/traces/`) works without it.
See `docs/EVALUATION.md` for where this fits in the EDD loop.

## Start / stop

```bash
podman compose -f infra/langfuse/docker-compose.yml up -d      # start (6 containers)
podman compose -f infra/langfuse/docker-compose.yml ps         # status
podman compose -f infra/langfuse/docker-compose.yml logs -f langfuse-web   # logs
podman compose -f infra/langfuse/docker-compose.yml down       # stop (keep data)
podman compose -f infra/langfuse/docker-compose.yml down -v    # stop + wipe data
```

UI: **http://localhost:3000**

## First-time onboarding (get your API keys)

1. Open http://localhost:3000 → **sign up** (local account, stays on your machine).
2. Create an **Organization**, then a **Project**.
3. Project → **Settings → API Keys → Create** → copy the **Public key** (`pk-lf-…`) and **Secret key** (`sk-lf-…`).
4. Paste them into the repo-root `.env`:
   ```
   LANGFUSE_HOST=http://localhost:3000
   LANGFUSE_PUBLIC_KEY=pk-lf-…
   LANGFUSE_SECRET_KEY=sk-lf-…
   ```
5. Ask a question via the CLI (`uv run python -m policy_copilot.cli "..."`) — the trace appears under your project in Langfuse.

## Notes

- **6 containers:** `langfuse-web`, `langfuse-worker`, `postgres`, `clickhouse`, `redis`, `minio`.
- ClickHouse host ports are intentionally **not** exposed (internal network only) to avoid a collision on host port 9000 — see the comment in `docker-compose.yml`.
- Default credentials in this compose are for **local use only** — never expose to a network.
- `docker-compose.yml` is vendored from [github.com/langfuse/langfuse](https://github.com/langfuse/langfuse) (self-host).
- If `LANGFUSE_PUBLIC_KEY` is unset, tracing silently falls back to JSONL only — nothing breaks.
