# Demo Script — Autonomous dbt Pipeline Healing with ArcAI

> **Audience:** Technical / data engineering audience, or executive with a technical escort
> **Duration:** 12–15 minutes including questions
> **Green flag moment:** GitHub PR opens in live terminal — zero human intervention

---

## Before You Start (5 min prep)

**Have open in this order:**

| Tab | What | URL / Command |
|-----|------|---------------|
| 1 | Snowflake — PIPELINE_RUN_LOG (failure state) | Snowflake UI → `DEMOP.DBT_PIPELINE.PIPELINE_RUN_LOG` |
| 2 | GitHub — before PR | `github.com/SAIRAMDHARMARAJAN/snowflake-dbt-healer/pulls` |
| 3 | Terminal — ready to run orchestrator | `cd ~/Downloads/arc-pipeline-healer` |
| 4 | VS Code — broken model SQL | `dbt_project/models/broken/mart_revenue_by_product.sql` |

**Pre-demo checklist:**
- [ ] MCP server running: `python3 mcp_server/server.py &` (port 8700)
- [ ] Broken model restored (`on o.product_sku = p.product_id` — the buggy line)
- [ ] At least one failure row in PIPELINE_RUN_LOG with `TRIGGERED_BY = 'dbt_scheduler'`
- [ ] Terminal font size bumped to 18pt (audience can read it)
- [ ] Slide deck on presenter display, demo on main screen

**Insert a failure row if needed:**
```sql
INSERT INTO DEMOP.DBT_PIPELINE.PIPELINE_RUN_LOG VALUES (
  UUID_STRING(),
  'mart_revenue_by_product',
  'failure',
  CURRENT_TIMESTAMP(),
  CURRENT_TIMESTAMP(),
  0,
  'Database Error in model mart_revenue_by_product: column "product_sku" of relation "stg_orders" does not exist',
  'dbt_scheduler'
);
```

---

## Act 1 — The Problem (2 min)

**[Slide: The Problem]**

> "Every data team has lived this. A dbt model fails overnight. Someone wakes up at 2am, reads logs, finds the broken SQL, figures out the fix, writes it, opens a PR. 30 to 90 minutes of an engineer's morning — for every failure.
>
> The root cause is almost always schema drift. An upstream column gets renamed. The mart model that joins on it doesn't know yet.
>
> Today I'm going to show you what happens when you take that entire loop — detect, diagnose, fix, verify, PR — and hand it to two ArcAI agents."

---

## Act 2 — The Architecture (3 min)

**[Slide: Technical Architecture]**

Walk through the diagram left to right:

> "Here's how it's wired.
>
> **Snowflake** on the left — that's where the data lives. A Snowflake Scheduled Task runs dbt every hour. When a model fails, the error goes straight into this table: `PIPELINE_RUN_LOG`. That's the trigger.
>
> **The Orchestrator** in the middle — that's a Python script. It polls Snowflake every five minutes, reads new failure rows, and coordinates what happens next.
>
> **ArcAI Platform** — two agents. The Inspector Agent gets the SQL and the error message, reasons over it with an LLM, and returns a structured JSON diagnosis: failure type, broken line, root cause, confidence level.
>
> The Healer Agent takes that diagnosis and fires six MCP tools. These are real tool calls — not prompts. Each one does exactly one thing: get the SQL, write the fix, run dbt, open the PR.
>
> **GitHub** on the right — that's the green flag. A PR opens with the full diff, the root cause, and proof that dbt passed. That's the audit trail."

---

## Act 3 — Show the Failure (1 min)

**[Switch to: Snowflake tab]**

> "Let's look at what triggered this. Here's the `PIPELINE_RUN_LOG` table."

Point to the failure row:

> "Status: failure. Error message: *column 'product_sku' does not exist*. Triggered by: `dbt_scheduler`. That row is what the orchestrator will find."

**[Switch to: VS Code — broken model SQL]**

> "Here's the broken model. `mart_revenue_by_product`. This is the dbt SQL that's failing.
>
> The join is: `on o.product_sku = p.product_id`
>
> Problem: `stg_orders` has no `product_sku` column and no `product_id` column. The correct shared key between these two tables is `product_category = category`. That's the schema drift. The upstream model was updated and the mart wasn't."

---

## Act 4 — Run the Demo (4 min, live)

**[Switch to: Terminal]**

> "Now I'll start the orchestrator. This is what would run automatically every five minutes in production."

```bash
python3 orchestrator.py
```

**Narrate as the output scrolls:**

```
[1/4] Gathering data from MCP...
```
> "Step one — the orchestrator calls MCP tools directly to get the SQL and the error history from Snowflake."

```
[2/4] Inspector Agent diagnosing...
```
> "Step two — the Inspector Agent. This is an ArcAI A2A endpoint. The orchestrator sends it the full SQL, the error message, and the run history. The LLM reads all of it and returns a structured diagnosis."

```
✅ Diagnosis: COLUMN_MISSING | confidence: HIGH
   Root cause: stg_orders has no product_sku column...
```
> "Failure type: COLUMN_MISSING. Confidence: HIGH. Auto-fixable: true. The Inspector found it."

```
[3/4] Applying fix and running dbt...
  ✅ SQL patched
  ✅ dbt run: PASSED
```
> "Step three — the Healer patches the SQL. Then runs dbt against Snowflake. It has to pass before we touch GitHub."

```
[4/4] Opening GitHub PR...
  ✅ PR opened: https://github.com/harshandev/arc-pipeline-healer/pull/2
```
> "PR is open."

---

## Act 5 — Show the Results (2 min)

**[Switch to: GitHub PR tab — refresh]**

> "Here's the PR. `fix(dbt): mart_revenue_by_product — COLUMN_MISSING fix`."

Point out:
- **The diff**: `on o.product_sku = p.product_id` → `on o.product_category = p.category`
- **The PR body**: root cause, before/after, dbt run verification status
- **Branch name**: `fix/dbt-mart_revenue_by_product-20261109...`

> "Full audit trail. Any engineer can open this PR and understand exactly what broke, why, and what was done. And they didn't have to wake up at 2am to write it."

**[Switch to: Snowflake tab — refresh PIPELINE_RUN_LOG]**

> "Back in Snowflake — the last row is now a success row, logged by the orchestrator. The table tells the full story: failure, then auto-heal."

---

## Act 6 — What Makes This Real (1 min)

**[Slide: Continuous Autonomy]**

> "This isn't a one-off script. The same loop runs every five minutes via `scheduler.sh`. When the next schema drift hits, the system finds it, fixes it, and opens the PR — without anyone getting paged.
>
> With Snowflake Enterprise, we can run this entirely serverlessly — the dbt Task triggers the orchestrator natively via External Access Integration. No external scheduler needed.
>
> The agent pair — Inspector and Healer — works on any dbt project. Point the MCP server at a different project path and you have the same coverage for every client pipeline."

---

## Q&A Cheat Sheet

| Question | Answer |
|----------|--------|
| What LLM powers the agents? | ArcAI uses whatever model is configured in the agent definition — in this case the default ArcAI LLM. The Inspector prompt is crafted to always return structured JSON, so the response is reliable. |
| What if the agent gets it wrong? | The dbt run step is a hard gate — if the fixed SQL doesn't pass dbt, the orchestrator stops and logs a failure. No PR is opened. The fix goes nowhere until it's verified. |
| What if it's not auto-fixable? | The Inspector sets `auto_fixable: false` and the orchestrator skips the fix, logs the diagnosis to Snowflake, and can be extended to page the on-call engineer with the full diagnosis attached. |
| Why not just use dbt Cloud's built-in alerts? | dbt Cloud can alert, but it can't fix. The agents + MCP server close the gap from "alert fired" to "PR open." |
| Can this work with dbt Cloud instead of dbt Core? | Yes — the MCP `run_dbt_model` tool calls the dbt CLI. Point it at dbt Cloud CLI or the dbt Cloud API and the rest of the loop is unchanged. |
| Why does the MCP server run locally / with ngrok? | Snowflake Trial doesn't support External Access Integration (outbound HTTP from Stored Procedures). With Snowflake Enterprise, the MCP server can run anywhere and be called directly from Snowflake. |
| What is MCP? | Model Context Protocol — an open standard from Anthropic for giving agents structured access to tools over HTTP (JSON-RPC). It's how the Healer Agent calls fix_model_sql, run_dbt_model, etc. |

---

## Timing Reference

| Act | Slide | Duration |
|-----|-------|----------|
| Intro + problem | 3 | 2 min |
| Architecture walkthrough | 5 | 3 min |
| Show the failure (Snowflake + VS Code) | — | 1 min |
| **Live orchestrator run** | — | **4 min** |
| Show results (GitHub PR + SF log) | 9 | 2 min |
| Continuous autonomy + next steps | 10–11 | 1 min |
| Q&A | — | 2–3 min |
| **Total** | | **~15 min** |

---

*Demo repo: `github.com/SAIRAMDHARMARAJAN/snowflake-dbt-healer`*
*ArcAI platform: `arcai-stage.solutions.growtharc.com`*
