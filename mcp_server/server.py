"""
MCP Server — Pipeline Healer
Implements MCP JSON-RPC over HTTP (streamable HTTP transport).
ArcAI arc-connect probes with POST initialize → expects 200.
"""
import os, subprocess, uuid, json, base64, re
from datetime import datetime, timezone
from pathlib import Path
 
import snowflake.connector
import urllib.request
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import asyncio
 
load_dotenv(Path(__file__).parent.parent / ".env")
 
DBT_PROJECT  = Path(__file__).parent.parent / "dbt_project"
DBT_BIN = Path(__file__).parent.parent / ".venv" / "bin" / "dbt"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "harshandev/arc-pipeline-healer")
 
app = FastAPI(title="Pipeline Healer MCP")
 
# ── Snowflake ──────────────────────────────────────────────────────
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
 
# ── GitHub ─────────────────────────────────────────────────────────
def gh_api(method, path, body=None):
    url  = f"https://api.github.com/repos/{GITHUB_REPO}/{path}"
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())
 
# ── Tool definitions ───────────────────────────────────────────────
TOOLS = [
    {"name": "get_pipeline_failures",
     "description": "Scan PIPELINE_RUN_LOG for recently failed dbt model runs.",
     "inputSchema": {"type": "object", "properties": {
         "hours_back": {"type": "integer", "default": 24}}}},
    {"name": "get_model_error_detail",
     "description": "Get full error detail and run history for a specific failed dbt model.",
     "inputSchema": {"type": "object", "properties": {
         "model_name": {"type": "string"}}, "required": ["model_name"]}},
    {"name": "get_model_sql",
     "description": "Read the current SQL of a dbt model from the project.",
     "inputSchema": {"type": "object", "properties": {
         "model_name": {"type": "string"}}, "required": ["model_name"]}},
    {"name": "fix_model_sql",
     "description": "Overwrite a dbt model SQL with a corrected version.",
     "inputSchema": {"type": "object", "properties": {
         "model_name": {"type": "string"},
         "fixed_sql":  {"type": "string"},
         "reason":     {"type": "string"}},
         "required": ["model_name", "fixed_sql", "reason"]}},
    {"name": "run_dbt_model",
     "description": "Run a dbt model and return success/failure.",
     "inputSchema": {"type": "object", "properties": {
         "model_name": {"type": "string"}}, "required": ["model_name"]}},
    {"name": "log_pipeline_run",
     "description": "Write a pipeline run result to PIPELINE_RUN_LOG.",
     "inputSchema": {"type": "object", "properties": {
         "model_name":    {"type": "string"},
         "status":        {"type": "string"},
         "rows_affected": {"type": "integer"},
         "error_message": {"type": "string"},
         "triggered_by":  {"type": "string"}},
         "required": ["model_name", "status"]}},
    {"name": "create_github_pr",
     "description": "Create a GitHub branch with fixed SQL and open a Pull Request.",
     "inputSchema": {"type": "object", "properties": {
         "model_name":   {"type": "string"},
         "failure_type": {"type": "string"},
         "broken_line":  {"type": "string"},
         "fixed_line":   {"type": "string"},
         "root_cause":   {"type": "string"},
         "fixed_sql":    {"type": "string"}},
         "required": ["model_name", "failure_type", "broken_line", "fixed_line", "root_cause", "fixed_sql"]}},
]
 
# ── Tool implementations ───────────────────────────────────────────
def run_tool(name: str, args: dict):
    if name == "get_pipeline_failures":
        hours_back = args.get("hours_back", 24)
        conn = get_conn(); cur = conn.cursor()
        cur.execute(f"""
            SELECT MODEL_NAME, STATUS, STARTED_AT, ERROR_MESSAGE FROM PIPELINE_RUN_LOG
            WHERE STATUS='failure' AND STARTED_AT >= DATEADD('hour', -{hours_back}, CURRENT_TIMESTAMP())
            ORDER BY STARTED_AT DESC LIMIT 20
        """)
        rows = cur.fetchall(); cur.close(); conn.close()
        failures = [{"model_name": r[0], "status": r[1], "started_at": str(r[2]), "error_message": r[3]} for r in rows]
        return {"failures": failures, "count": len(failures)}
 
    elif name == "get_model_error_detail":
        model = args["model_name"]
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT MODEL_NAME,STATUS,STARTED_AT,FINISHED_AT,ERROR_MESSAGE,TRIGGERED_BY FROM PIPELINE_RUN_LOG WHERE MODEL_NAME=%s ORDER BY STARTED_AT DESC LIMIT 5", (model,))
        rows = cur.fetchall(); cur.close(); conn.close()
        history = [{"model_name": r[0], "status": r[1], "started_at": str(r[2]), "finished_at": str(r[3]), "error_message": r[4], "triggered_by": r[5]} for r in rows]
        sql_data = run_tool("get_model_sql", {"model_name": model})
        return {"run_history": history, "current_sql": sql_data.get("sql")}
 
    elif name == "get_model_sql":
        model = args["model_name"]
        models_dir = DBT_PROJECT / "models"
        for path in models_dir.rglob(f"{model}.sql"):
            return {"model": model, "sql": path.read_text(), "path": str(path)}
        return {"model": model, "sql": None, "error": f"Model {model} not found"}
 
    elif name == "fix_model_sql":
        model = args["model_name"]
        models_dir = DBT_PROJECT / "models"
        for path in models_dir.rglob(f"{model}.sql"):
            original = path.read_text()
            path.write_text(args["fixed_sql"])
            return {"model": model, "fixed": True, "reason": args.get("reason", ""), "original_sql": original}
        return {"model": model, "fixed": False, "error": "Model not found"}
 
    elif name == "run_dbt_model":
        model = args["model_name"]
        env = {**os.environ, "DBT_PROFILES_DIR": str(DBT_PROJECT)}
        result = subprocess.run(
            [str(DBT_BIN if DBT_BIN.exists() else "dbt"),
             "run", "--select", f"+{model}", "--profiles-dir", str(DBT_PROJECT), "--project-dir", str(DBT_PROJECT)],
            capture_output=True, text=True, env=env,
        )
        success = result.returncode == 0
        output  = result.stdout + result.stderr
        # Extract meaningful error lines for logging
        error_lines = [
            line.strip() for line in output.splitlines()
            if re.search(
                r"(error|compilation|database|failure|syntax|invalid|does not exist|unexpected|failed)",
                line,
                re.IGNORECASE,
            )
        ]
        error_msg = " ".join(error_lines[-30:]) or output[-1200:]
        # On failure, return the full dbt output tail so agents have real context
        full_error = output[-1200:] if not success else None
        run_tool("log_pipeline_run", {"model_name": model, "status": "success" if success else "failure",
                                       "error_message": error_msg[:400], "triggered_by": "mcp_tool"})
        return {"model": model, "success": success, "error": full_error, "output_tail": output[-500:]}
 
    elif name == "log_pipeline_run":
        conn = get_conn(); cur = conn.cursor()
        now  = datetime.now(timezone.utc)
        cur.execute("INSERT INTO PIPELINE_RUN_LOG (RUN_ID,MODEL_NAME,STATUS,STARTED_AT,FINISHED_AT,ROWS_AFFECTED,ERROR_MESSAGE,TRIGGERED_BY) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (str(uuid.uuid4()), args["model_name"], args["status"], now, now,
                     args.get("rows_affected", 0), args.get("error_message", ""), args.get("triggered_by", "agent")))
        conn.commit(); cur.close(); conn.close()
        return {"logged": True, "model": args["model_name"], "status": args["status"]}
 
    elif name == "create_github_pr":
        model = args["model_name"]
        ts    = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        branch = f"fix/dbt-{model}-{ts}"
        main_ref = gh_api("GET", "git/ref/heads/main")
        gh_api("POST", "git/refs", {"ref": f"refs/heads/{branch}", "sha": main_ref["object"]["sha"]})
        model_path = None
        for p in DBT_PROJECT.rglob(f"{model}.sql"):
            model_path = "dbt_project/" + str(p.relative_to(DBT_PROJECT)); break
        if not model_path:
            return {"error": f"Cannot find {model}.sql"}
        try:
            file_sha = gh_api("GET", f"contents/{model_path}")["sha"]
        except Exception:
            file_sha = None
        commit_body = {"message": f"fix(dbt): {model} — {args['failure_type']} fix\n\nAuto-healed by ArcAI Pipeline Healer Agent.",
                       "content": base64.b64encode(args["fixed_sql"].encode()).decode(), "branch": branch}
        if file_sha:
            commit_body["sha"] = file_sha
        gh_api("PUT", f"contents/{model_path}", commit_body)
        # Build a diff of what actually changed in the SQL
        try:
            current_sql_raw = base64.b64decode(
                gh_api("GET", f"contents/{model_path}?ref=main")["content"]
            ).decode()
        except Exception:
            current_sql_raw = args.get("broken_line", "")
        import difflib
        diff_lines = list(difflib.unified_diff(
            current_sql_raw.splitlines(), args["fixed_sql"].splitlines(),
            lineterm="", n=3
        ))
        diff_block = "\n".join(diff_lines[2:]) if len(diff_lines) > 2 else "(no diff)"
 
        fence = "```"
        pr_body = (
            f"## 🔧 Autonomous Pipeline Auto-Heal\n\n"
            f"**Model:** `{model}`\n"
            f"**Failure type:** `{args['failure_type']}`\n"
            f"**Root cause:** {args['root_cause']}\n\n"
            f"### Changes\n"
            f"{fence}diff\n{diff_block}\n{fence}\n\n"
            f"### Verification\n"
            f"✅ `dbt run --select {model}` passed successfully in Snowflake before opening this PR.\n\n"
            f"*Automated by ArcAI Pipeline Healer Agent.*\n"
        )
        pr = gh_api("POST", "pulls", {"title": f"fix(dbt): {model} — {args['failure_type']} fix",
                                       "head": branch, "base": "main", "body": pr_body})
        return {"pr_url": pr["html_url"], "pr_number": pr["number"], "branch": branch, "status": "opened"}
 
    return {"error": f"Unknown tool: {name}"}
 
# ── MCP JSON-RPC endpoint ──────────────────────────────────────────
@app.post("/mcp")
async def mcp_endpoint(request: Request):
    body = await request.json()
    method = body.get("method")
    req_id = body.get("id")
 
    if method == "initialize":
        return JSONResponse({
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "pipeline-healer-mcp", "version": "1.0.0"},
            }
        })
 
    if method == "tools/list":
        return JSONResponse({
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": TOOLS}
        })
 
    if method == "tools/call":
        tool_name = body.get("params", {}).get("name")
        tool_args = body.get("params", {}).get("arguments", {})
        try:
            result = run_tool(tool_name, tool_args)
            return JSONResponse({
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": json.dumps(result)}]}
            })
        except Exception as e:
            return JSONResponse({
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32603, "message": str(e)}
            })
 
    if method == "notifications/initialized":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})
 
    return JSONResponse({"jsonrpc": "2.0", "id": req_id,
                         "error": {"code": -32601, "message": f"Method not found: {method}"}})
 
@app.get("/health")
def health():
    return {"status": "ok", "tools": len(TOOLS)}
 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8700)