# Performance Optimization Guide

## Current Baseline

From benchmark run on 2026-06-03:
- **Latency (p50)**: 4 ms
- **Latency (p95)**: 7 ms
- **Pass rate**: 100% (22/22 queries)
- **Execution accuracy**: 100%

## Profiling Your Agent

### 1. Run Latency Profiler

```powershell
$env:PYTHONPATH="src"
.\venv\Scripts\python -c @"
import time
from app.agents.query_orchestrator import QueryOrchestrator

questions = [
    'What were total sales by product category?',
    'Show me the top 5 products by revenue',
    'What is the average order value by region?'
]

orchestrator = QueryOrchestrator()
for q in questions:
    start = time.time()
    response = orchestrator.process_question(q)
    elapsed = (time.time() - start) * 1000
    print(f'{q}: {elapsed:.1f}ms')
"@
```

### 2. Database Query Performance

```sql
-- Test slow queries on database
SELECT * FROM PRODUCT_SALES_DATASET_FINAL WHERE 1=0;

-- Check table stats
SELECT table_name, num_rows FROM user_tables;

-- Check indexes
SELECT * FROM user_indexes;
```

### 3. Memory Profiling

```powershell
$env:PYTHONPATH="src"
.\venv\Scripts\pip install memory-profiler psutil
.\venv\Scripts\python -m memory_profiler scripts/demo_pipeline.py
```

## Optimization Strategies

### A. Database Optimizations

1. **Create indexes** on frequently filtered columns:
   ```sql
   CREATE INDEX idx_order_date ON PRODUCT_SALES_DATASET_FINAL(ORDER_DATE);
   CREATE INDEX idx_category ON PRODUCT_SALES_DATASET_FINAL(CATEGORY);
   ```

2. **Materialized views** for common aggregations:
   ```sql
   CREATE MATERIALIZED VIEW sales_by_category AS
   SELECT CATEGORY, SUM(REVENUE) as total_revenue
   FROM PRODUCT_SALES_DATASET_FINAL
   GROUP BY CATEGORY;
   ```

3. **Connection pooling tuning** in `.env`:
   ```
   AGENT_DB_CONNECT_RETRIES=6
   AGENT_QUERY_TIMEOUT_SECONDS=15
   AGENT_MAX_ROWS_RETURNED=500
   ```

### B. Agent Optimizations

1. **Cache RAG documents**:
   - Reduce embedding lookups
   - Store frequently used schema in memory

2. **Reduce LLM calls**:
   - Use prompt caching
   - Batch similar questions

3. **Parallelize retrieval**:
   - Fetch docs + schema in parallel
   - Execute SQL + formatting in parallel

### C. API Optimizations

1. **Enable caching** in FastAPI:
   ```python
   from fastapi_cache2 import FastAPICache
   from fastapi_cache2.backends.redis import RedisBackend
   
   @app.get("/query", response_model=dict)
   @cached(expire=3600)  # Cache for 1 hour
   async def cached_query(question: str):
       ...
   ```

2. **Add response compression**:
   ```python
   from fastapi.middleware.gzip import GZIPMiddleware
   app.add_middleware(GZIPMiddleware, minimum_size=1000)
   ```

3. **Use async endpoints**:
   ```python
   @app.post("/query")
   async def process_query(request: QueryRequest):
       orchestrator = QueryOrchestrator()
       response = await asyncio.to_thread(orchestrator.process_question, request.question)
       return response
   ```

## Monitoring in Production

### 1. Add APM (Application Performance Monitoring)

```powershell
.\venv\Scripts\pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-jaeger
```

### 2. Log query performance

In `app/sql/executor.py`, add timing:
```python
import time
import logging

logger = logging.getLogger(__name__)

start = time.time()
cursor.execute(sql)
results = cursor.fetchall()
elapsed = time.time() - start
logger.info(f"Query executed in {elapsed:.3f}s: {sql[:100]}")
```

### 3. Set up alerts

```yaml
# Example Prometheus alerts
groups:
  - name: sql_agent
    rules:
      - alert: SlowQuery
        expr: query_duration_seconds > 10
        for: 5m
```

## Load Testing

### Generate load with Apache JMeter or k6:

```javascript
// load-test.js (for k6)
import http from 'k6/http';
import { check } from 'k6';

export let options = {
  vus: 10,
  duration: '30s',
};

export default function () {
  let res = http.post('http://localhost:8000/query', JSON.stringify({
    question: 'What were total sales by product category?'
  }), {
    headers: { 'Content-Type': 'application/json' },
  });
  
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response time < 5s': (r) => r.timings.duration < 5000,
  });
}
```

Run: `k6 run load-test.js`

## Benchmarks to Track

| Metric | Target | Current |
|--------|--------|---------|
| p50 latency | < 10ms | 4ms ✅ |
| p95 latency | < 50ms | 7ms ✅ |
| p99 latency | < 500ms | - |
| DB connections | < 4 | - |
| Memory per request | < 100MB | - |
| Pass rate | > 95% | 100% ✅ |

