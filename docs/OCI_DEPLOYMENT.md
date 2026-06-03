# Deploying on OCI + Oracle Autonomous Database

How to run this as a real service against Oracle Autonomous Database (ADB) and
OCI Generative AI, and the concrete gaps to close before it is production-grade.

## 1. As-deployed architecture

```
Streamlit UI ──HTTP──► FastAPI /query (sql_agent.api.routes)
                          │
                          ▼
              app.production_pipeline.answer_question
                          │  picks backend by config
        ┌─────────────────┴───────────────────────────┐
   OCI configured                              not configured
        ▼                                            ▼
 app.agents.query_orchestrator.QueryOrchestrator     app.pipeline.FullPipeline
   • OracleRAGRetriever  ─► OCI GenAI embeddings        (DuckDB over db/seed CSV;
       (cohere.embed-english-v3.0) + 23ai               offline demo / CI only)
       VECTOR_DISTANCE(... COSINE)
   • OracleSelectAISQLGenerator ─► DBMS_CLOUD_AI.GENERATE (Select AI)
   • SafeSQLExecutor ─► Autonomous DB (read-only, row cap, timeout)
   • ConversationMemory (multi-turn)
                          │
        result + deterministic insights/chart (summariser) ─► QueryResponse
```

"OCI configured" = `ADB_DSN` set **and** (`SELECT_AI_PROFILE` or `OCI_COMPARTMENT_ID`),
or `DEPLOY_TARGET=oracle` to force it. Otherwise the API serves the offline
DuckDB pipeline (useful for CI and laptops, **not** for production).

## 2. OCI services used

| Service | Used for | Code |
|---|---|---|
| Autonomous Database (23ai) | SQL execution + `VECTOR` store for RAG docs | `app/sql/oracle_connection.py`, `app/rag/retriever.py` |
| OCI Generative AI – embeddings | `cohere.embed-english-v3.0` (1024-dim) | `app/rag/oci_embeddings.py` |
| Oracle Select AI (`DBMS_CLOUD_AI`) | NL→SQL generation + answer narration | `app/sql/generator.py`, `app/agents/summariser.py` |
| Object Storage | staging the seed/raw CSV before `seed_database.py` | `scripts/seed_database.py` |

## 3. Build & run

```bash
# Build the image (now copies app/, evaluation/, db/, data/ — see Dockerfile)
docker build -t ocir.<region>.ocir.io/<tenancy>/sql-agent:1.0 .

# Run locally against ADB (wallet mounted read-only, secrets via env_file)
docker compose up           # api on :8000, ui on :8501

# Push to OCI Registry, then deploy to OKE / Container Instances
docker push ocir.<region>.ocir.io/<tenancy>/sql-agent:1.0
```

Required env (see `.env.example`): `ADB_USER` (read-only), `ADB_PASSWORD`,
`ADB_DSN`, `ADB_WALLET_LOCATION`, `SELECT_AI_PROFILE`, `OCI_COMPARTMENT_ID`,
`OCI_CONFIG_PATH`/profile (or instance principals — see §4), `OCI_EMBED_MODEL_ID`.

## 4. Where to improve — prioritised (production gaps)

### P0 — correctness / security (do first)

1. **Authentication + rate limiting on `/query`.** The endpoint is open and
   `CORSMiddleware(allow_origins=["*"])`. Put it behind **OCI API Gateway** with
   an auth policy (OAuth2/JWT) and per-client rate limits; lock CORS to the UI origin.
2. **Secrets in OCI Vault, not `.env`.** `ADB_PASSWORD` and the wallet password
   are plaintext env today. Move them to **OCI Vault**; inject at runtime. Mount
   the ADB wallet from an **OCI secret / volume**, never bake it into the image
   (the Dockerfile no longer copies it; compose mounts `./wallet:ro`).
3. **Use resource/instance principals for OCI GenAI.** `oci_embeddings.py`
   requires an `OCI_CONFIG_PATH` file. On OKE/Compute, switch to
   `oci.auth.signers.get_resource_principals_signer()` (no config file, no keys
   on the box). Suggested patch:
   ```python
   # app/rag/oci_embeddings.py
   if os.getenv("OCI_AUTH") == "resource_principal":
       signer = oci.auth.signers.get_resource_principals_signer()
       self.config = {"region": signer.region}
       self.client = GenerativeAiInferenceClient(config={}, signer=signer,
           service_endpoint=f"https://inference.generativeai.{signer.region}.oci.oraclecloud.com")
   ```
4. **Least-privilege DB user.** Keep `ADB_USER=sql_agent_readonly`; grant only
   `CREATE SESSION` + `SELECT` on the demo schema (and on `APP_RAG_DOCUMENTS`).
   The executor already enforces read-only + `max_rows` + `call_timeout`, but the
   DB grant is the real backstop.

### P1 — reliability / scale

5. **Connection pool sizing.** `oracle_connection.get_adb_pool` uses `min=0,
   max=4`. `min=0` means a cold first query; `max=4` caps concurrency. Make them
   env-driven (`min=1, max=10`) and run uvicorn with `--workers N` behind the
   gateway; size the pool per worker.
6. **Turn the demo cache OFF in prod.** `app/sql/fallbacks.py` returns hardcoded
   category rows when ADB fails — fine for a rehearsed demo, dangerous in prod
   (stale numbers presented as real). Gate it on `DEMO_FALLBACK_ENABLED=false`
   (already in `.env.example`) and assert it's false in production config.
7. **Async / blocking.** FastAPI is sync; ADB + Select AI calls block the event
   loop. Wrap DB/LLM calls in `asyncio.to_thread` or use `oracledb` async, or run
   enough workers to absorb it. Add a request-level timeout above the DB timeout.

### P2 — observability / cost

8. **Wire the observability that's already designed.** Send `structlog` JSON to
   **OCI Logging**, request/latency/error metrics to **OCI Monitoring**, and a
   per-request token-cost counter (`llm/token_counter.py`) — the design exists in
   `observability/README.md`; it just isn't emitting yet.
9. **Embeddings cost.** RAG docs are embedded once at seed time (good). Make sure
   `RAG_AUTO_SEED_ON_STARTUP=false` in prod and seed via a one-off job, so every
   pod restart doesn't re-embed. Cache query embeddings for repeated questions.
10. **Health/readiness split.** `/health` is liveness; add a `/ready` that checks
    ADB pool + OCI reachability so OKE doesn't route traffic before the pool warms.

## 5. What was fixed in this pass

- **Container now contains the runtime.** The Dockerfile previously copied only
  `src/`, so the API's `import app.pipeline` failed in-container and it silently
  served the **stub** responder. It now copies `app/ evaluation/ db/ data/`, sets
  `PYTHONPATH=/app:/app/src`, runs as non-root, and has a `HEALTHCHECK`. Compose
  mounts the same plus the wallet read-only. `duckdb` added to dependencies.
- **The API now hits Oracle, not a CSV.** `routes.py` previously called
  `FullPipeline`, which executes against the **DuckDB seed**, so a "deployed on
  Oracle" API answered from a static snapshot. It now calls
  `app.production_pipeline.answer_question`, which routes to the live
  **QueryOrchestrator** (ADB + Select AI + 23ai vector) when OCI is configured and
  enriches the result with deterministic insights + a chart spec, falling back to
  the offline pipeline (and finally the stub) only when nothing else is available.
- Fixed a stale `LangChainRAGRetriever` import in `app/pipeline.py` (the class was
  renamed `OracleRAGRetriever`), which had silently disabled retrieval.

## 6. One-glance production checklist

- [ ] API Gateway + auth + rate limit; CORS locked to UI origin
- [ ] Secrets in OCI Vault; wallet from secret/volume; resource principals for GenAI
- [ ] `sql_agent_readonly` granted SELECT-only
- [ ] `DEMO_FALLBACK_ENABLED=false`, `RAG_AUTO_SEED_ON_STARTUP=false`, `DEPLOY_TARGET=oracle`
- [ ] Pool `min>=1`, sized per worker; uvicorn `--workers`
- [ ] structlog → OCI Logging; metrics → OCI Monitoring; token-cost counter on
- [ ] `/ready` checks ADB + OCI; OKE liveness/readiness probes
- [ ] `make benchmark` with creds (`mode=live_oci`) captured as the accuracy number
