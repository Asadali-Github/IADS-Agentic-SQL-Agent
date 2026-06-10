# Deployment

## Local (no Docker)

Run the two processes in separate terminals:

```bash
# Terminal 1 — API
uvicorn sql_agent.api.main:app --reload --port 8000

# Terminal 2 — Frontend
streamlit run frontend/streamlit_app.py
```

Open **http://localhost:8501** in your browser.

---

## Local (Docker)

```bash
cp .env.example .env   # fill in your values first
docker compose up --build
```

- API available at **http://localhost:8000**
- UI available at **http://localhost:8501**

To stop: `docker compose down`

---

## OCI — Compute VM (demo day target)

### Topology

One VM runs both containers via Docker Compose.  
The UI container reaches the API container by the `api` service name (internal Docker network — no public port needed for the API).

### Required environment variables

Copy `.env.example` to `.env` on the VM and fill in every value before starting.

| Variable | What it is |
|---|---|
| `OCI_COMPARTMENT_ID` | OCID of your OCI compartment |
| `OCI_REGION` | e.g. `uk-london-1` |
| `OCI_GENAI_MODEL_ID` | LLM model — `cohere.command-r-plus` |
| `OCI_EMBED_MODEL_ID` | Embedding model — `cohere.embed-english-v3.0` |
| `OCI_CONFIG_PATH` | Path to `~/.oci/config` on the VM |
| `ADB_USER` | Autonomous DB username |
| `ADB_PASSWORD` | Autonomous DB password |
| `ADB_DSN` | DB connection string e.g. `yourdb_high` |
| `ADB_WALLET_LOCATION` | Path to the wallet directory on the VM |
| `DEMO_FALLBACK_ENABLED` | Keep `false` in dev; flip to `true` just before the live demo |
| `API_URL` | Set to `http://api:8000` inside Docker (already wired in docker-compose.yml) |

### Deployment steps

1. SSH into the VM.
2. Clone the repo: `git clone <repo-url> && cd IADS-Agentic-SQL-Agent`
3. Copy and fill in the env file: `cp .env.example .env`
4. Place the OCI wallet files in `./wallet/` and the OCI config at `~/.oci/config`.
5. Build and start: `docker compose up --build -d`
6. Verify both containers are healthy: `docker compose ps`
7. Open the VM's public IP on port 8501 in your browser.

### Demo cache failover

If the live DB becomes unreachable during the demo:

```bash
# On the VM, edit .env and set:
DEMO_FALLBACK_ENABLED=true
# Then restart:
docker compose restart api
```

The UI's demo mode toggle in the sidebar does the same thing from the browser once Abdul Qayyum wires it up.

---

## CI/CD

The `.github/workflows/ci.yml` pipeline runs on every push and PR to `main`:

1. **Install** — `pip install -e ".[dev]"`
2. **Lint** — `ruff check src tests`
3. **Type check** — `mypy src` (non-blocking during the hackathon)
4. **Tests** — `pytest` (runs both unit and integration suites)

Keep the pipeline green before merging anything. If a test fails after Omar swaps the stub for the real orchestrator, the end-to-end tests in `tests/integration/test_end_to_end.py` will tell you exactly which field broke.
