# Complete Setup & Architecture Guide

## System Overview

The IADS Agentic SQL Agent is a multi-stage AI system that converts natural language questions into SQL queries, executes them against an Oracle Autonomous Database, and returns business-friendly answers.

```
User Question
    ↓
[RAG Retriever] → Fetches relevant schema & examples
    ↓
[LLM SQL Generator] → Uses Oracle Select AI to generate SQL
    ↓
[SQL Validator] → Ensures query safety and correctness
    ↓
[Query Executor] → Runs SQL on Oracle ADB
    ↓
[Answer Summarizer] → Converts results to natural language
    ↓
[Streamlit Frontend] or [FastAPI REST API]
```

## Architecture Components

### 1. Data Pipeline (`app/pipeline.py`)

**Responsibility**: Orchestrate the multi-stage query processing

**Flow**:
1. Load `.env` configuration
2. Initialize connections (Oracle, OCI)
3. Process question through stages
4. Return structured response

**Key Classes**:
- `QueryOrchestrator`: Main orchestration class
- `Pipeline`: Base pipeline implementation

### 2. Agents (`app/agents/`)

#### Query Orchestrator (`query_orchestrator.py`)
- Coordinates all components
- Maintains conversation context
- Routes between fallback strategies

#### Support Guard (`support_guard.py`)
- Validates if a question is answerable
- Returns appropriate error messages

#### Summariser (`summariser.py`)
- Converts query results to plain English
- Uses OCI GenAI to generate natural language answers

#### Memory (`memory.py`)
- Maintains conversation history
- Provides context for multi-turn conversations

### 3. RAG System (`app/rag/`)

#### Retriever (`retriever.py`)
- Fetches relevant documents using vector similarity
- Sources:
  - Schema descriptions (`db/schema_descriptions.yaml`)
  - SQL examples (`data/placeholder_docs.json`)
  - Business rules and KPIs

#### Embeddings (`embeddings.py`)
- Uses OCI Generative AI embeddings
- Caches embeddings in memory for performance

#### Documents (`documents.py`)
- Loads and manages document corpus
- Formats results for prompt injection

### 4. SQL Processing (`app/sql/`)

#### Generator (`generator.py`)
- Uses Oracle Select AI for SQL generation
- Inputs: Question + Retrieved context
- Output: Safe SQL query

#### Validator (`validator.py`)
- Performs safety checks:
  - Only SELECT statements allowed
  - No table modifications
  - Row limit enforcement (max 500)
- Parses SQL AST to verify safety

#### Executor (`executor.py`)
- Executes validated SQL
- Returns structured results
- Handles connection retries

#### Oracle Connection (`oracle_connection.py`)
- Manages connection pooling
- Handles wallet-based authentication
- Auto-retry on failure

#### Prompt Builder (`prompt_builder.py`)
- Constructs prompts with context
- Formats schema information
- Injects few-shot examples

### 5. Frontend

#### Streamlit App (`frontend/streamlit_app.py`)
- Interactive web UI
- Chat-like interface
- Real-time streaming of results
- Demo mode with cached results

#### FastAPI Backend (`app/main.py`)
- REST API for programmatic access
- Health checks
- Query endpoints

### 6. Data Assets (`data/` & `db/`)

#### Schema (`db/schema_descriptions.yaml`)
```yaml
tables:
  PRODUCT_SALES_DATASET_FINAL:
    description: "Product-level order transactions"
    columns:
      - name: CATEGORY
        description: "Product category (Electronics, Home, etc.)"
```

#### Documents (`data/placeholder_docs.json`)
- Example queries
- Business rules
- Common patterns

#### Raw Data (`data/raw/product_sales_dataset_final.csv`)
- 200,000 sales records
- Used for development and testing

### 7. Evaluation (`evaluation/`)

#### Benchmark (`benchmark.py`)
- Tests agent on golden query set
- Metrics:
  - Execution accuracy
  - SQL AST equivalence
  - Partial match (row recall)
  - Latency measurements

#### Metrics (`metrics.py`)
- Scoring functions
- Comparison algorithms

## Configuration

### Environment Variables (`.env`)

```env
# OCI Identity & Access
OCI_COMPARTMENT_ID=ocid1.compartment.oc1...
OCI_REGION=uk-london-1
OCI_CONFIG_PATH=C:\Users\asadc\.oci\config
OCI_CONFIG_PROFILE=DEFAULT

# OCI GenAI Models
OCI_GENAI_MODEL_ID=meta.llama-3.3-70b-instruct
OCI_EMBED_MODEL_ID=cohere.embed-english-v3.0

# Oracle Autonomous Database
ADB_USER=ADMIN
ADB_PASSWORD=EssexTeam4!123
ADB_DSN=hackatondb_high
ADB_WALLET_LOCATION=./wallet
ADB_WALLET_PASSWORD=Wallet123!

# Agent Behavior
AGENT_MAX_RETRIES=3
AGENT_QUERY_TIMEOUT_SECONDS=15
AGENT_MAX_ROWS_RETURNED=500
VECTOR_FALLBACK_ENABLED=true
DEMO_FALLBACK_ENABLED=false
SCHEMA_OBFUSCATION_ENABLED=false
FEW_SHOT_ENABLED=true
ROUTER_ENABLED=false

# API & Logging
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

### Key Features

| Feature | Status | Config Key |
|---------|--------|-----------|
| RAG (Schema Retrieval) | ✅ Active | N/A |
| Vector Search | ✅ Active | N/A |
| SQL Generation (Select AI) | ✅ Active | N/A |
| SQL Validation | ✅ Active | N/A |
| Answer Summarization | ✅ Active | N/A |
| Fallback to Demo Data | ✅ Available | `DEMO_FALLBACK_ENABLED` |
| Conversation Memory | ✅ Active | N/A |
| Multi-turn Context | ✅ Active | N/A |

## Data Flow Example

**User Question**: "What were total sales by product category?"

1. **RAG Retrieval**:
   - Vector search for "sales category"
   - Returns 4 documents:
     - Example SQL pattern
     - Table schema
     - Column definitions
     - Business rules

2. **SQL Generation**:
   - LLM receives:
     ```
     Question: What were total sales by product category?
     Context: [Retrieved docs]
     ```
   - Generates:
     ```sql
     SELECT CATEGORY, SUM(REVENUE) AS total_revenue
     FROM PRODUCT_SALES_DATASET_FINAL
     GROUP BY CATEGORY
     ORDER BY total_revenue DESC
     FETCH FIRST 100 ROWS ONLY
     ```

3. **Validation**:
   - ✅ Only SELECT: PASS
   - ✅ No modifications: PASS
   - ✅ Row limit: 100 < 500: PASS

4. **Execution**:
   - Runs query on Oracle ADB
   - Returns 4 rows:
     - Electronics: $57.5M
     - Home & Furniture: $47.7M
     - Clothing: $27.1M
     - Accessories: $10.1M

5. **Summarization**:
   - LLM receives results + question
   - Generates:
     ```
     "The leading product category in terms of total sales 
      is Electronics at $57.5M, followed by Home & Furniture 
      at $47.7M, Clothing & Apparel at $27.1M, and Accessories 
      at $10.1M."
     ```

## Performance Characteristics

### Latency Profile

| Component | Typical Time |
|-----------|------------|
| RAG Retrieval | 10-50ms |
| SQL Generation | 500-2000ms |
| SQL Execution | 100-500ms |
| Summarization | 500-1500ms |
| **Total** | **1.1-4.0s** |

### Scalability

- **Concurrent Users**: 10+ (depending on LLM quota)
- **Connection Pool**: 4 (configurable)
- **Max Rows Returned**: 500 (configurable)
- **Query Timeout**: 15s (configurable)

## Customization Points

### 1. Modify Prompts
Edit files in `prompts/`:
- `sql_generation.md` - SQL generation logic
- `sql_explanation.md` - SQL explanation
- `summariser.md` - Answer generation

### 2. Add New RAG Documents
- Update `data/placeholder_docs.json`
- Re-embed with `scripts/embed_schema.py`
- System automatically uses new documents

### 3. Change LLM Models
Update `.env`:
```env
OCI_GENAI_MODEL_ID=meta.llama-3-70b-instruct  # Change to different model
```

Available models:
- `meta.llama-3.3-70b-instruct` (recommended)
- `cohere.command-r-plus`
- `mistral.large`

### 4. Adjust Safety Constraints
```env
AGENT_MAX_ROWS_RETURNED=1000  # Increase from 500
AGENT_QUERY_TIMEOUT_SECONDS=30  # Increase from 15
```

### 5. Add New Data Sources
1. Create schema description in `db/schema_descriptions.yaml`
2. Add example queries to `data/placeholder_docs.json`
3. Restart agent

## Testing & Validation

### Unit Tests
```bash
.\venv\Scripts\pytest tests/unit/
```

### Integration Tests
```bash
.\venv\Scripts\pytest tests/integration/
```

### Benchmark
```bash
$env:PYTHONPATH="src"
.\venv\Scripts\python scripts/run_benchmark.py
```

Expected: 100% pass rate (22/22 questions)

## Troubleshooting

### Issue: "Database not connected"

**Solution**:
```bash
.\venv\Scripts\python test_connection.py

# Should output:
# OCI config valid
# ADB connected - 200000 rows found...
# Select AI working
```

### Issue: Slow queries (>5 seconds)

**Check**:
1. Network latency to OCI
2. LLM response time (use models like `command-r-plus` for speed)
3. Database query execution time

**Optimize**:
- Enable vector caching
- Use connection pooling
- Add database indexes

### Issue: Out of memory

**Reduce**:
- `AGENT_MAX_ROWS_RETURNED` (from 500)
- LLM cache size
- Embedding cache

## Next Steps

1. **Deploy**: Use Docker Compose or Kubernetes
2. **Monitor**: Add logging and APM
3. **Scale**: Add load balancer and replicas
4. **Customize**: Adjust prompts and business logic
5. **Integrate**: Connect to existing systems via REST API

See also:
- [Docker Deployment Guide](DOCKER_DEPLOYMENT.md)
- [Performance Optimization Guide](PERFORMANCE.md)
- [OCI Deployment Guide](OCI_DEPLOYMENT.md)

