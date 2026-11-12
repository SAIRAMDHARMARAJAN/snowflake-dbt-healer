"""
Simulate a full pipeline run:
  - Runs healthy models (stg_orders, stg_customers, mart_revenue_daily)
  - Runs broken model (mart_revenue_by_product) which fails
  - Logs everything to PIPELINE_RUN_LOG

This is the trigger the Inspector Agent monitors.
"""
import sys, os
from pathlib import Path

# Auto-detect and switch to .venv python if running under global python
_venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python3"
if _venv_python.exists() and sys.executable != str(_venv_python):
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

import uuid, subprocess
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import snowflake.connector

load_dotenv(Path(__file__).parent.parent / ".env")

DBT_PROJECT = Path(__file__).parent.parent / "dbt_project"

def get_conn():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema="DBT_PIPELINE",
    )

def log_run(model, status, rows=0, error="", triggered_by="scheduler"):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    cur.execute("""
        INSERT INTO PIPELINE_RUN_LOG
            (RUN_ID, MODEL_NAME, STATUS, STARTED_AT, FINISHED_AT,
             ROWS_AFFECTED, ERROR_MESSAGE, TRIGGERED_BY)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (str(uuid.uuid4()), model, status, now, now, rows, error, triggered_by))
    conn.commit(); cur.close(); conn.close()

def run_model(model_name):
    env = {**os.environ, "DBT_PROFILES_DIR": str(DBT_PROJECT)}
    result = subprocess.run(
        ["dbt", "run", "--select", model_name,
         "--profiles-dir", str(DBT_PROJECT),
         "--project-dir", str(DBT_PROJECT)],
        capture_output=True, text=True, env=env,
    )
    return result.returncode == 0, result.stdout + result.stderr

MODELS = [
    "stg_orders",
    "stg_customers",
    "stg_products",
    "mart_revenue_daily",
    "mart_customer_lifetime_value",
    "mart_revenue_by_product",   # this one breaks
]

print("=" * 60)
print("Pipeline run starting:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
print("=" * 60)

for model in MODELS:
    print(f"\n  Running {model}...", end=" ", flush=True)
    success, output = run_model(model)
    if success:
        print("✓ SUCCESS")
        log_run(model, "success", rows=100, triggered_by="scheduler")
    else:
        error_lines = [l for l in output.split("\n") if "Error" in l or "error" in l]
        error_msg = " | ".join(error_lines[:3]) if error_lines else output[-400:]
        print(f"✗ FAILED")
        print(f"    Error: {error_msg[:120]}")
        log_run(model, "failure", error=error_msg[:800], triggered_by="scheduler")

print("\n" + "=" * 60)
print("Pipeline run complete. Check PIPELINE_RUN_LOG for failures.")
print("=" * 60)
