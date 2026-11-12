#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  ArcAI Pipeline Healer — ONE-COMMAND DEMO STARTUP
#  Run this before every demo.  It does everything.
#  Usage: bash start.sh
# ═══════════════════════════════════════════════════════════════════

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ -f "$DIR/.venv/bin/activate" ]; then
  source "$DIR/.venv/bin/activate"
fi

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}══ $1 ══${NC}"; }
ok()     { echo -e "  ${GREEN}✅ $1${NC}"; }
warn()   { echo -e "  ${YELLOW}⚠️  $1${NC}"; }
fail()   { echo -e "  ${RED}❌ $1${NC}"; exit 1; }
info()   { echo -e "  ${CYAN}→  $1${NC}"; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   ArcAI Pipeline Healer — Demo Startup Script   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ── STEP 1: Check .env ────────────────────────────────────────────
banner "Step 1 — Checking credentials"
if [ ! -f "$DIR/.env" ]; then
  fail ".env file not found. Copy .env.example to .env and fill in your credentials."
fi
ok ".env found"

# Source env for validation
export $(grep -v '^#' "$DIR/.env" | xargs)

[ -z "$SNOWFLAKE_ACCOUNT" ]  && fail "SNOWFLAKE_ACCOUNT missing in .env"
[ -z "$ARCAI_API_KEY" ]      && fail "ARCAI_API_KEY missing in .env"
[ -z "$GITHUB_TOKEN" ]       && fail "GITHUB_TOKEN missing in .env"
ok "All required credentials present"

# ── STEP 2: Install Python dependencies ───────────────────────────
banner "Step 2 — Python dependencies"
if ! python3 -c "import snowflake.connector, fastapi, uvicorn, dotenv" 2>/dev/null; then
  info "Installing requirements..."
  pip3 install -r "$DIR/requirements.txt" -q
  ok "Dependencies installed"
else
  ok "Dependencies already installed"
fi

# ── STEP 3: Optionally seed the demo model ────────────────────────
banner "Step 3 — Preparing demo model"
BROKEN_SQL="$DIR/dbt_project/models/broken/mart_revenue_by_product.sql"

if [ "${RESET_BROKEN_MODEL:-false}" = "true" ]; then
cat > "$BROKEN_SQL" << 'SQLEOF'
select
    o.order_date,
    p.product_name,
    p.category,
    p.unit_price,
    count(distinct o.order_id) as total_orders,
    sum(o.amount)              as total_revenue
from {{ ref('stg_orders') }} o
inner join {{ ref('stg_products') }} p
    on o.product_sku = p.product_id   -- BUG: use o.product_category = p.category instead
group by 1, 2, 3, 4
SQLEOF

  ok "mart_revenue_by_product.sql reset to BROKEN state"
  info "Bug: 'on o.product_sku = p.product_id' — column product_sku does not exist"
else
  ok "Keeping existing model SQL (set RESET_BROKEN_MODEL=true only for the demo reset)"
fi

# ── STEP 4: Insert fresh failure row in Snowflake ─────────────────
banner "Step 4 — Seeding Snowflake PIPELINE_RUN_LOG with failure"
python3 - << 'PYEOF'
import os, uuid, snowflake.connector
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path('.env'), override=True)

conn = snowflake.connector.connect(
    account=os.environ['SNOWFLAKE_ACCOUNT'],
    user=os.environ['SNOWFLAKE_USER'],
    password=os.environ['SNOWFLAKE_PASSWORD'],
    role=os.environ['SNOWFLAKE_ROLE'],
    warehouse=os.environ['SNOWFLAKE_WAREHOUSE'],
    database=os.environ['SNOWFLAKE_DATABASE'],
    client_session_keep_alive=False,
)
cur = conn.cursor()
cur.execute("CREATE SCHEMA IF NOT EXISTS DBT_PIPELINE")
cur.execute("USE SCHEMA DBT_PIPELINE")
cur.execute("""
CREATE TABLE IF NOT EXISTS PIPELINE_RUN_LOG (
    RUN_ID          VARCHAR(36),
    MODEL_NAME      VARCHAR(100),
    STATUS          VARCHAR(20),
    STARTED_AT      TIMESTAMP_NTZ,
    FINISHED_AT     TIMESTAMP_NTZ,
    ROWS_AFFECTED   INT,
    ERROR_MESSAGE   VARCHAR(2000),
    TRIGGERED_BY    VARCHAR(50)
)
""")
now = datetime.now(timezone.utc)
cur.execute(
    "INSERT INTO PIPELINE_RUN_LOG VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
    (
        str(uuid.uuid4()),
        'mart_revenue_by_product',
        'failure',
        now, now, 0,
        'Database Error in model mart_revenue_by_product: column "product_sku" of relation "stg_orders" does not exist\nLINE 10:     on o.product_sku = p.product_id',
        'dbt_scheduler',
    )
)
conn.commit()
cur.close(); conn.close()
print("  ✅ Failure row inserted into PIPELINE_RUN_LOG")
os._exit(0)
PYEOF

# ── STEP 5: Kill any old MCP server and start fresh ───────────────
banner "Step 5 — Starting MCP server (port 8700)"
OLD_PID=$(lsof -ti:8700 2>/dev/null || true)
if [ -n "$OLD_PID" ]; then
  kill "$OLD_PID" 2>/dev/null && info "Killed old process on port 8700 (PID $OLD_PID)"
  sleep 1
fi

mkdir -p "$DIR/logs"
python3 "$DIR/mcp_server/server.py" > "$DIR/logs/mcp_server.log" 2>&1 &
MCP_PID=$!
echo "$MCP_PID" > "$DIR/logs/mcp_server.pid"
sleep 2

# Verify it started
if curl -s http://localhost:8700/health > /dev/null 2>&1; then
  ok "MCP server running on port 8700 (PID $MCP_PID)"
else
  fail "MCP server failed to start. Check logs/mcp_server.log"
fi

# ── STEP 6: Verify ArcAI agents are reachable ─────────────────────
banner "Step 6 — Checking ArcAI agent connectivity"
python3 - << 'PYEOF'
import os, requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path('.env'), override=True)
key = os.environ.get('ARCAI_API_KEY', '')
headers = {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

for name, url_key in [('Inspector', 'INSPECTOR_A2A_URL'), ('Healer', 'HEALER_A2A_URL')]:
    url = os.environ.get(url_key, '').replace('/runs', '')
    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code in (200, 404, 405):
            print(f"  ✅ {name} Agent reachable ({r.status_code})")
        else:
            print(f"  ⚠️  {name} Agent returned {r.status_code} — check API key")
    except Exception as e:
        print(f"  ⚠️  {name} Agent not reachable: {e}")
PYEOF

# ── STEP 7: Final readiness summary ───────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║            ✅  DEMO SYSTEM READY                 ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}What's running:${NC}"
echo -e "  🟢 MCP Server           → http://localhost:8700/health"
echo -e "  🟢 Broken model         → mart_revenue_by_product.sql (buggy state)"
echo -e "  🟢 Snowflake log        → 1 fresh failure row seeded"
echo ""
echo -e "${BOLD}Demo steps:${NC}"
echo -e "  1. Show Snowflake PIPELINE_RUN_LOG (failure row is there)"
echo -e "  2. Show VS Code — mart_revenue_by_product.sql (broken join)"
echo -e "  3. Run:  ${CYAN}python3 orchestrator.py${NC}"
echo -e "  4. Show GitHub PR that opens automatically"
echo -e "  5. Refresh Snowflake — success row now appears"
echo ""
echo -e "${BOLD}Logs:${NC}  tail -f logs/mcp_server.log"
echo -e "${BOLD}Stop:${NC}  kill \$(cat logs/mcp_server.pid)"
echo ""
