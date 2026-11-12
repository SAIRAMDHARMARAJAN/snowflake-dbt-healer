"""
Pipeline Healer Orchestrator
Reads failures from Snowflake → calls MCP tools directly for data →
sends rich context to ArcAI agents for LLM reasoning → applies fix → opens GitHub PR.
"""
import os, json, requests, re
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path
 
load_dotenv(Path(__file__).parent / ".env", override=True)
 
INSPECTOR_URL = os.environ["INSPECTOR_A2A_URL"]
HEALER_URL    = os.environ["HEALER_A2A_URL"]
ARCAI_KEY     = os.environ["ARCAI_API_KEY"]
MCP_URL       = "http://localhost:8700/mcp"
 
ARCAI_HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {ARCAI_KEY}",
    "Prefer": "wait=60",
}
 
# ── MCP tool caller (direct, local) ───────────────────────────────
def mcp(tool_name, args=None):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": tool_name, "arguments": args or {}}}
    r = requests.post(MCP_URL, json=payload, timeout=60)
    r.raise_for_status()
    content = r.json().get("result", {}).get("content", [{}])
    text = content[0].get("text", "{}") if content else "{}"
    return json.loads(text)
 
# ── ArcAI agent caller ─────────────────────────────────────────────
def call_agent(url, message):
    resp = requests.post(url, headers=ARCAI_HEADERS,
                         json={"input": {"message": message}}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "completed":
        raw = data.get("output", {}).get("content", "")
        # Extract JSON block from agent reply
        m = re.search(r'\{[^{}]*"model_name"[^{}]*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        # Wider search
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
        return {"raw": raw, "status": data.get("status")}
    return {"error": data.get("error"), "status": data.get("status")}
 
# ── Snowflake: get failures ────────────────────────────────────────
def get_failures():
    import snowflake.connector
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"], role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"], database=os.environ["SNOWFLAKE_DATABASE"],
        schema="DBT_PIPELINE",
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT MODEL_NAME, ERROR_MESSAGE, STARTED_AT FROM PIPELINE_RUN_LOG
        WHERE STATUS = 'failure' AND TRIGGERED_BY = 'dbt_scheduler'
        ORDER BY STARTED_AT DESC LIMIT 5
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{"model_name": r[0], "error_message": r[1], "started_at": str(r[2])} for r in rows]

def discover_models():
    models_dir = Path(__file__).parent / "dbt_project" / "models"
    return sorted(path.stem for path in models_dir.rglob("*.sql") if path.is_file())

def detect_current_failures():
    """Run every model on disk; do not rely on a folder name or old log row."""
    failures = []
    models = discover_models()
    print(f"Checking all {len(models)} dbt model(s) in dbt_project/models...")
    for model in models:
        result = mcp("run_dbt_model", {"model_name": model})
        if not result.get("success", False):
            failures.append({
                "model_name": model,
                "error_message": result.get("error") or result.get("output_tail") or "dbt run failed",
                "started_at": str(datetime.now(timezone.utc)),
            })
    return failures

def log_result(model_name, status, summary):
    import snowflake.connector, uuid
    conn = snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"], role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"], database=os.environ["SNOWFLAKE_DATABASE"],
        schema="DBT_PIPELINE",
    )
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute(
        "INSERT INTO PIPELINE_RUN_LOG VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (str(uuid.uuid4()), model_name, status, now, now, 0, summary[:500], "arcai_orchestrator")
    )
    conn.commit(); cur.close(); conn.close()
 
# ── Main ───────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("ArcAI Pipeline Healer — Orchestrator")
    print("=" * 60)
 
    # Always test the current project. Historical rows can be stale and cannot
    # describe edits made after the last scheduler run.
    failures = detect_current_failures()
    if not failures:
        print("✅ No failures found — all current pipelines healthy.")
        return
 
    print(f"Found {len(failures)} failure(s):\n")
    for f in failures:
        print(f"  ❌ {f['model_name']}: {f['error_message'][:80]}")
 
    # Deduplicate by model name
    seen = set()
    unique = [f for f in failures if f["model_name"] not in seen and not seen.add(f["model_name"])]
 
    for failure in unique:
        model = failure["model_name"]
        error = failure["error_message"]
        print(f"\n{'─'*60}\nProcessing: {model}\n{'─'*60}")
 
        # ── Step 1: Gather data via MCP directly ──────────────────
        print("\n[1/4] Gathering data from MCP...")
        sql_data    = mcp("get_model_sql", {"model_name": model})
        current_sql = sql_data.get("sql", "SQL not found")
 
        # Run dbt NOW to get the real current error (not the stale Snowflake log)
        live_run = mcp("run_dbt_model", {"model_name": model})
        if live_run.get("success"):
            print(f"  ✅ dbt run passed — no active failure for {model}, skipping.")
            continue
        live_error = live_run.get("error") or error
        print(f"  ✅ SQL retrieved ({len(current_sql)} chars) | Live error captured")
 
        error = live_error  # use the real current error for the agent
 
        # ── Step 2: Inspector Agent — LLM reasoning ───────────────
        print("\n[2/4] Inspector Agent diagnosing...")
        inspector_msg = f"""You are diagnosing a failed dbt pipeline model.
 
MODEL: {model}
 
LIVE ERROR (from dbt right now):
{error}
 
CURRENT SQL (exactly as it is on disk right now):
{current_sql}
 
Your job: carefully read the ENTIRE SQL line by line.
dbt only reports the FIRST error it hits — there may be more errors after it.
Find and fix ALL syntax errors, missing keywords, wrong columns, and malformed clauses in one pass.
Do not stop at the first error — scan the whole SQL.
Produce ONLY a JSON diagnosis (no other text).
Choose a descriptive failure_type based only on the live evidence; do not force
the error into a fixed enum. State the exact failing token, column, relation,
line, or dbt operation when the output provides it. Do NOT reference previous
errors or history — only what you see above.
 
{{
  "model_name": "{model}",
  "failure_type": "<specific failure category>",
  "issues": [{{"description": "<specific issue>", "evidence": "<exact dbt evidence>"}}],
  "broken_line": "<exact line from SQL that is wrong>",
  "root_cause": "<plain English: what is actually wrong in the SQL>",
  "suggested_fix": "<what to change>",
  "confidence": "HIGH",
  "auto_fixable": true,
  "fixed_sql": "<the complete corrected SQL>"
}}"""
 
        diagnosis = call_agent(INSPECTOR_URL, inspector_msg)
        if "error" in diagnosis and "raw" not in diagnosis:
            print(f"  ❌ Inspector failed: {diagnosis}")
            log_result(model, "failure", f"Inspector failed: {diagnosis}")
            continue
 
        print(f"  ✅ Diagnosis: {diagnosis.get('failure_type','?')} | confidence: {diagnosis.get('confidence','?')}")
        print(f"     Root cause: {diagnosis.get('root_cause','')[:100]}")
 
        fixed_sql = diagnosis.get("fixed_sql") or ""
        # If agent didn't return complete fixed SQL, derive it from broken_line + suggested_fix
        if not fixed_sql or fixed_sql == current_sql:
            print(f"  ⚠  Generating fix from agent suggested_fix...")
            broken     = diagnosis.get("broken_line", "").strip()
            suggestion = diagnosis.get("suggested_fix", "").strip()
            if broken and suggestion and broken in current_sql:
                broken_bare = broken.split("--")[0].strip()
                for line in current_sql.splitlines():
                    if broken_bare and broken_bare in line:
                        fixed_sql = current_sql.replace(line.rstrip(), suggestion)
                        break
                else:
                    fixed_sql = current_sql.replace(broken, suggestion)
            else:
                fixed_sql = current_sql
        if not diagnosis.get("auto_fixable", True):
            print("  ⚠️  auto_fixable=false — attempting fix anyway (dbt is the safety gate)")
 
        # ── Step 3: Apply fix and run dbt — retry up to 3 times ──
        print("\n[3/4] Applying fix and running dbt...")
        success = False
        run_result = {}
        for attempt in range(1, 4):
            fix_result = mcp("fix_model_sql", {
                "model_name": model,
                "fixed_sql": fixed_sql,
                "reason": diagnosis.get("root_cause", "auto-heal"),
            })
            print(f"  ✅ SQL patched (attempt {attempt}): {fix_result.get('fixed', False)}")
 
            run_result = mcp("run_dbt_model", {"model_name": model})
            success = run_result.get("success", False)
            print(f"  {'✅' if success else '❌'} dbt run attempt {attempt}: {'PASSED' if success else 'FAILED'}")
            if success:
                break
 
            remaining_error = run_result.get("error") or run_result.get("output_tail", "") or ""
            print(f"     Error: {remaining_error[:150]}")
            if attempt < 3:
                print(f"\n  ↻ Remaining errors — sending back to Inspector (pass {attempt+1}/3)...")
                current_sql_now = mcp("get_model_sql", {"model_name": model}).get("sql", fixed_sql)
                retry_msg = f"""You are fixing a dbt pipeline model. A previous fix was applied but dbt STILL fails.
 
MODEL: {model}
 
REMAINING ERROR after last fix:
{remaining_error}
 
CURRENT SQL (with partial fix already applied):
{current_sql_now}
 
Your job: carefully read the ENTIRE SQL line by line.
Find and fix ALL remaining syntax errors, missing keywords, wrong columns, and malformed clauses.
Return ONLY a JSON object — no other text.
 
{{
  "model_name": "{model}",
  "failure_type": "<SYNTAX_ERROR|COLUMN_MISSING|JOIN_ERROR|AGGREGATION_ERROR|OTHER>",
  "broken_line": "<exact line still wrong>",
  "root_cause": "<what is still wrong>",
  "suggested_fix": "<what to change>",
  "confidence": "HIGH",
  "auto_fixable": true,
  "fixed_sql": "<the complete corrected SQL with ALL errors fixed>"
}}"""
                retry_diag = call_agent(INSPECTOR_URL, retry_msg)
                new_fixed = retry_diag.get("fixed_sql", "")
                if new_fixed and new_fixed != current_sql_now:
                    fixed_sql = new_fixed
                    print(f"     Root cause: {retry_diag.get('root_cause','')[:100]}")
                else:
                    print("     ⚠  Agent returned no new fix — stopping retries.")
                    break
 
        if not success:
            print(f"     ❌ All fix attempts exhausted.")
            log_result(model, "failure", f"dbt run failed after fix: {run_result.get('error','')[:200]}")
            continue
 
        # ── Step 4: Open GitHub PR via MCP ────────────────────────
        print("\n[4/4] Opening GitHub PR...")
        pr_result = mcp("create_github_pr", {
            "model_name": model,
            "failure_type": diagnosis.get("failure_type", "COLUMN_MISSING"),
            "broken_line": diagnosis.get("broken_line", ""),
            "fixed_line": diagnosis.get("suggested_fix", ""),
            "root_cause": diagnosis.get("root_cause", ""),
            "fixed_sql": fixed_sql,
        })
        pr_url = pr_result.get("pr_url", "N/A")
        print(f"  ✅ PR opened: {pr_url}")
 
        log_result(model, "success", f"Auto-healed. PR: {pr_url}. {diagnosis.get('root_cause','')[:200]}")
 
    print(f"\n{'='*60}")
    print("Orchestrator run complete.")
    print("SELECT * FROM PIPELINE_RUN_LOG ORDER BY STARTED_AT DESC;")
 
if __name__ == "__main__":
    main()