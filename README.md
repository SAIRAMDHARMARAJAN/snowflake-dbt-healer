# ArcAI Pipeline Healer

Autonomous dbt pipeline failure detection and self-healing via ArcAI A2A agents, 
orchestrated entirely from Snowflake.

## Architecture

```
Snowflake Task (hourly cron)
  └── CALL HEAL_PIPELINE(inspector_url, healer_url)
        └── Scans PIPELINE_RUN_LOG for failures
        └── SYSTEM$HTTP_REQUEST → Inspector Agent A2A URL
              └── Diagnoses every evidenced error from model SQL + run output
              └── Returns structured diagnosis JSON
        └── SYSTEM$HTTP_REQUEST → Healer Agent A2A URL  
              └── Applies safe SQL/dbt fixes via MCP Server
              └── Re-runs dbt and iterates on remaining model-local errors
              └── Opens GitHub PR with fix
        └── Logs outcome back to PIPELINE_RUN_LOG
```

## Setup

### 1. Snowflake
```bash
cd ~/growtharc/arc-pipeline-healer
python3 scripts/seed_snowflake.py        # creates tables + 500 rows synthetic data
```

### 2. dbt models
```bash
cd dbt_project
dbt run --select stg_orders stg_customers stg_products mart_revenue_daily mart_customer_lifetime_value --profiles-dir .
# mart_revenue_by_product is intentionally broken — the agents will fix it
```

### 3. MCP Server
```bash
uvicorn mcp_server.server:app --port 8700 --reload
# Test: curl http://localhost:8700/tools
```

`start.sh` preserves the current model SQL by default. To intentionally reset
the demo model to its sample broken state, run:

```bash
RESET_BROKEN_MODEL=true ./start.sh
```

The orchestrator scans every `.sql` file below `dbt_project/models`,
regardless of whether it is in `broken`, `staging`, or `marts`. It runs each
current model and sends the live dbt output and exact SQL to the inspector, so
old `PIPELINE_RUN_LOG` messages cannot replace the current error.

### GitHub sync

This project is connected to
`https://github.com/SAIRAMDHARMARAJAN/snowflake-dbt-healer`. To continuously
commit and push local code changes:

```bash
./scripts/watch_and_push.sh
```

The watcher checks every 10 seconds by default. Set
`SYNC_INTERVAL_SECONDS=30` to change the interval. Credentials, `.venv`,
logs, and dbt build artifacts are excluded from commits.

### 4. ArcAI Studio
1. Create **Inspector Agent** — paste contents of `agents/inspector_agent.md` as system prompt
2. Add MCP Server: `http://localhost:8700`
3. Enable A2A — copy the Inspector A2A URL
4. Create **Healer Agent** — paste contents of `agents/healer_agent.md` as system prompt  
5. Add same MCP Server
6. Enable A2A — copy the Healer A2A URL

### 5. Snowflake SP + Task
```sql
-- Run in order:
-- snowflake/01_setup_network_rule.sql   (once, as ACCOUNTADMIN)
-- snowflake/02_heal_pipeline_sp.sql     (creates HEAL_PIPELINE procedure)
-- snowflake/03_pipeline_task.sql        (creates + activates the task)
--   ↑ paste your A2A URLs from Step 4 into this file first
```

### 6. Trigger a demo run
```sql
-- In Snowflake worksheet:
EXECUTE TASK PIPELINE_HEALER_TASK;

-- Watch it work:
SELECT * FROM PIPELINE_RUN_LOG ORDER BY STARTED_AT DESC;
```

## What happens

| Model | Expected |
|---|---|
| stg_orders | ✅ passes |
| stg_customers | ✅ passes |
| stg_products | ✅ passes |
| mart_revenue_daily | ✅ passes |
| mart_customer_lifetime_value | ✅ passes |
| mart_revenue_by_product | ❌ fails — `product_sku` column doesn't exist |

The Inspector Agent identifies the actual failure category and all evidenced
issues. The Healer Agent applies safe fixes, reruns the model, iterates on any
remaining model-local errors, and opens a GitHub PR only after verification
passes. External failures or ambiguous business decisions are reported for
human review instead of being guessed.
