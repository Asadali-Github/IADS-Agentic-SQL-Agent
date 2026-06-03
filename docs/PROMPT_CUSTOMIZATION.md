# Prompt Customization Guide

## Overview

The agent's behavior is driven by prompts stored in `prompts/` directory. Each prompt is a markdown template that guides the LLM to perform specific tasks.

## Prompt Files

### 1. SQL Generation (`prompts/sql_generation.md`)

**Purpose**: Guides LLM to generate safe, correct SQL from natural language

**Current Status**: Placeholder (being used from code)

**Example Template**:
```markdown
# sql_generation

You are an enterprise SQL generation agent.

**Task**: Convert the user question into safe, optimized SELECT SQL.

**Rules**:
- Only SELECT statements allowed
- Max {{ max_rows }} rows returned
- Use provided table and column names exactly
- Include appropriate WHERE and GROUP BY clauses
- Optimize for readability and performance

**Context**:
Tables available:
{{ schema_info }}

Business rules:
{{ business_rules }}

Example patterns:
{{ example_queries }}

**User Question**:
{{ question }}

**Output Format**:
Return JSON: {"sql": "SELECT ...", "explanation": "..."}
```

**Customization Ideas**:
- Add industry-specific rules
- Enforce particular SQL style/formatting
- Add complexity constraints
- Include query optimization hints

### 2. SQL Explanation (`prompts/sql_explanation.md`) ✅

**Purpose**: Explain generated SQL in business language

**Current Template**:
```markdown
You are explaining a database query to a business manager.

Given the question, schema, and SQL, write 2-4 bullet points
explaining HOW the query works (not WHAT it does).

Rules:
- No SQL jargon (no WHERE, GROUP BY, JOIN terms)
- Use business language
- Explain: what records we looked at, how we filtered, how we combined
```

**Customization Examples**:

**For Financial Domain**:
```markdown
When explaining financial queries, include:
- Which financial periods are included
- Whether amounts are aggregated or individual transactions
- Currency and any unit conversions applied
```

**For Sales Domain**:
```markdown
When explaining sales queries, emphasize:
- Which sales channels are included
- Time period of data
- Whether discounts are included
```

### 3. Summariser (`prompts/summariser.md`) ✅

**Purpose**: Convert SQL results to a single-sentence answer

**Current Template**:
```markdown
Turn the SQL result rows into ONE plain-English sentence answering the user's question.

Rules:
- Direct answer only
- Quote key numbers or names
- No table/column references
- If empty result, say plainly "no matching records"
```

**Customization Examples**:

**For Executive Summaries**:
```markdown
Generate a brief executive summary in 2-3 sentences including:
- Key finding
- Magnitude/impact
- Any significant trends or anomalies
```

**For Detailed Reports**:
```markdown
Write a detailed paragraph explaining:
- Main finding and supporting data
- Top 3 sub-findings
- Any caveats or limitations
```

### 4. Planner (`prompts/planner.md`)

**Purpose**: Placeholder - Could route complex questions to multi-step workflows

**Future Use**:
```markdown
# Query Planner

When a question requires multiple steps, create an execution plan:

Step 1: [First query]
Step 2: [Use results from step 1 to do...]
Step 3: [Final aggregation/answer]

Example:
Q: "Which product categories had growing revenue YoY?"
Step 1: Get category revenue for current year
Step 2: Get category revenue for previous year
Step 3: Calculate YoY growth by category
```

### 5. Critic (`prompts/critic.md`)

**Purpose**: Placeholder - Could validate agent outputs

**Future Use**:
```markdown
# Query Critic

Review the generated SQL for:
- Correctness: Does it answer the question?
- Completeness: Are all relevant records included?
- Efficiency: Is the query optimized?
- Safety: Could this harm data integrity?

Return: {"is_valid": true/false, "issues": [...]}
```

### 6. SQL Correction (`prompts/sql_correction.md`)

**Purpose**: Fix generated SQL that failed validation

**Future Use**:
```markdown
# SQL Error Recovery

The SQL below failed. Analyze the error and generate a corrected version.

Error: {{ error_message }}
Original SQL: {{ failed_sql }}

Return corrected SQL.
```

## How to Modify Prompts

### Step 1: Edit the Template File

```bash
# Open the prompt file
code prompts/sql_generation.md
```

### Step 2: Update Template Variables

Use `{{ variable }}` syntax for values injected at runtime:

```markdown
Select {{ limit }} rows from {{ table_name }}
where {{ column }} matches user criteria
```

**Available Variables**:
- `{{ question }}` - User's question
- `{{ schema_info }}` - Available tables/columns
- `{{ business_rules }}` - Domain rules
- `{{ example_queries }}` - Few-shot examples
- `{{ max_rows }}` - Row limit from config
- `{{ error_message }}` - Previous error (for correction)

### Step 3: Test the Changes

```bash
# Test with specific question
$env:PYTHONPATH="src"
.\venv\Scripts\python -c @"
from app.agents.query_orchestrator import QueryOrchestrator
orchestrator = QueryOrchestrator()
response = orchestrator.process_question('What are total sales by category?')
print(response['answer'])
"@
```

### Step 4: Validate in Benchmark

```bash
$env:PYTHONPATH="src"
.\venv\Scripts\python scripts/run_benchmark.py

# Check if pass_rate stayed at 100%
```

## Common Customizations

### 1. Add Industry-Specific Language

**For Healthcare**:
```markdown
When generating queries:
- Always filter for HIPAA-compliant views
- Include de-identification of patient records
- Reference medical codes (ICD-10, CPT) correctly
```

**For Financial Services**:
```markdown
When generating queries:
- Include regulatory timeframes (SEC filing dates)
- Account for trading halts and market hours
- Include compliance flags in results
```

### 2. Change Answer Format

**Current (Narrative)**:
```
"Electronics had the highest sales at $57.5M"
```

**Alternative (Bullet Points)**:
```markdown
Modify summariser.md to return:
- Top category: Electronics ($57.5M)
- Runner-up: Home & Furniture ($47.7M)
- Growth: +12% YoY
```

**Alternative (JSON)**:
```json
{
  "top_category": "Electronics",
  "revenue": 57485698.06,
  "ranking": [...]
}
```

### 3. Enforce SQL Style

```markdown
# SQL Style Guide

All generated SQL must:
- Use uppercase keywords (SELECT, WHERE, etc.)
- Qualify all columns with table alias
- Include column aliases for aggregates
- Use meaningful table aliases (NOT a, b, c)
- Order clauses: SELECT, FROM, WHERE, GROUP BY, ORDER BY

Example:
SELECT 
  p.category,
  SUM(p.revenue) as total_revenue
FROM product_sales p
WHERE p.order_date >= '2024-01-01'
GROUP BY p.category
ORDER BY total_revenue DESC
```

### 4. Add Guardrails

```markdown
# Safety Checks

Before returning SQL, verify:
- [ ] No subqueries accessing sensitive tables
- [ ] No joins to audit/log tables without explicit permission
- [ ] Row limits respect performance SLAs
- [ ] Aggregations include appropriate grouping

Reject query if any check fails.
```

## Advanced: Prompt Engineering Techniques

### 1. Chain-of-Thought Reasoning

```markdown
Before generating SQL, think through:
1. What is the user asking?
2. What tables contain this data?
3. How should the data be filtered?
4. What groupings/aggregations are needed?
5. What sorting makes sense?

Then, generate SQL based on this reasoning.
```

### 2. Few-Shot Learning

Add examples to the prompt:

```markdown
# Example Queries

Example 1:
Q: "Top 5 products by revenue?"
Schema: products (id, name, revenue), orders (id, product_id)
SQL: SELECT p.name, SUM(o.revenue) FROM products p JOIN orders o...

Example 2:
Q: "Revenue by month?"
Schema: orders (id, order_date, revenue)
SQL: SELECT DATE_TRUNC(order_date, MONTH), SUM(revenue)...
```

### 3. Constraint-Based Generation

```markdown
# Hard Constraints
These MUST be satisfied:
- [ ] Query must return < {{ max_rows }} rows
- [ ] Query must complete in < {{ timeout_sec }} seconds
- [ ] Query must not access PII tables
- [ ] Query must be deterministic (no RAND())
```

### 4. Self-Correction Loop

```markdown
# Validation Loop

1. Generate initial SQL
2. Check: Does it answer the question?
3. Check: Are all tables/columns valid?
4. Check: Is it safe to execute?
5. If any check fails, generate correction
6. Return final SQL
```

## Monitoring Prompt Effectiveness

### Track These Metrics

```python
# In your application
import json
from datetime import datetime

# Log each prompt execution
log = {
    "timestamp": datetime.now().isoformat(),
    "question": user_question,
    "prompt_version": "2.1",
    "sql_generated": generated_sql,
    "execution_time_ms": 1234,
    "success": True,
    "user_satisfaction": 5  # 1-5 star rating
}

# Analyze:
# - Accuracy rate by prompt version
# - Average latency per prompt
# - Common failure patterns
# - User feedback correlation
```

## Integrating New Prompts

If you create new prompt files:

1. **Register in code**:

```python
# app/sql/prompt_builder.py
PROMPTS = {
    'sql_generation': load_prompt('prompts/sql_generation.md'),
    'sql_explanation': load_prompt('prompts/sql_explanation.md'),
    'summariser': load_prompt('prompts/summariser.md'),
    'my_custom_prompt': load_prompt('prompts/my_custom_prompt.md'),  # New
}
```

2. **Use in pipeline**:

```python
# Example usage
rendered = PROMPTS['my_custom_prompt'].render(
    question=user_question,
    schema_info=schema,
    context=retrieved_docs
)
result = llm.invoke(rendered)
```

3. **Test thoroughly**:

```bash
$env:PYTHONPATH="src"
.\venv\Scripts\python -m pytest tests/ -v
```

## Best Practices

✅ **DO**:
- Keep prompts concise and clear
- Use specific examples
- Include both positive and negative examples
- Version control prompt changes
- Test before deploying
- Document what changed and why

❌ **DON'T**:
- Use overly complex language
- Leave ambiguous instructions
- Make prompts longer than necessary
- Modify prompts without testing
- Forget to update documentation

## Resources

- [OpenAI Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
- [Anthropic Prompt Engineering](https://docs.anthropic.com/en/docs/build-a-bot)
- [Ollama Prompt Tuning](https://github.com/ollama/ollama/blob/main/docs/prompts.md)

