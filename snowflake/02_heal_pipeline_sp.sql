-- Step 2: The main stored procedure
-- Detects pipeline failures and calls ArcAI agents via A2A to heal them

USE ROLE ACCOUNTADMIN;
USE DATABASE DEMOP;
USE SCHEMA DBT_PIPELINE;

CREATE OR REPLACE PROCEDURE HEAL_PIPELINE(
    INSPECTOR_A2A_URL   VARCHAR,   -- paste Inspector Agent A2A URL from ArcAI Studio
    HEALER_A2A_URL      VARCHAR,   -- paste Healer Agent A2A URL from ArcAI Studio
    HOURS_BACK          INT DEFAULT 24
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'requests')
EXTERNAL_ACCESS_INTEGRATIONS = (arcai_access_integration)
SECRETS = ('arcai_key=arcai_api_key')
HANDLER = 'heal_pipeline'
AS
$$
import _snowflake
import json
import requests
from datetime import datetime, timezone

def heal_pipeline(session, inspector_a2a_url, healer_a2a_url, hours_back=24):

    # ── Get ArcAI API key from Snowflake secret ────────────────────
    api_key = _snowflake.get_generic_secret_string('arcai_key')
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }

    results = []

    # ── Step 1: Find failures in PIPELINE_RUN_LOG ──────────────────
    failures_df = session.sql(f"""
        SELECT MODEL_NAME, ERROR_MESSAGE, STARTED_AT
        FROM PIPELINE_RUN_LOG
        WHERE STATUS = 'failure'
          AND STARTED_AT >= DATEADD('hour', -{hours_back}, CURRENT_TIMESTAMP())
        ORDER BY STARTED_AT DESC
        LIMIT 10
    """).collect()

    if not failures_df:
        return {'status': 'no_failures', 'message': 'All pipelines healthy', 'checked_at': str(datetime.now(timezone.utc))}

    for row in failures_df:
        model_name  = row['MODEL_NAME']
        error_msg   = row['ERROR_MESSAGE']

        # ── Step 2: Call Inspector Agent via A2A ───────────────────
        inspector_payload = {
            'message': f"""
                Diagnose this dbt pipeline failure:
                Model: {model_name}
                Error: {error_msg}

                Call get_model_error_detail for model '{model_name}' to get the full SQL,
                then produce a structured diagnosis JSON. Detect the actual failure
                from the error and SQL rather than assuming a predefined category.
                Include failure_type, issues, broken_line, root_cause, suggested_fix,
                confidence, auto_fixable, and complete fixed_sql fields. List every
                independent issue supported by evidence and do not guess.
            """,
            'context': {
                'model_name': model_name,
                'error_message': error_msg,
            }
        }

        inspector_response = requests.post(
            inspector_a2a_url,
            headers=headers,
            json=inspector_payload,
            timeout=120,
        )
        inspector_response.raise_for_status()
        diagnosis = inspector_response.json()

        # ── Step 3: Call Healer Agent via A2A ──────────────────────
        healer_payload = {
            'message': f"""
                Fix this broken dbt pipeline model using the diagnosis below.
                Apply all safe, evidence-based fixes, run the model to verify, and
                if verification reports another model-local error, diagnose and fix
                that too before opening a GitHub PR. Do not guess at external or
                business-rule failures.

                Diagnosis:
                {json.dumps(diagnosis, indent=2)}
            """,
            'context': {
                'diagnosis': diagnosis,
                'model_name': model_name,
            }
        }

        healer_response = requests.post(
            healer_a2a_url,
            headers=headers,
            json=healer_payload,
            timeout=180,
        )
        healer_response.raise_for_status()
        heal_result = healer_response.json()

        # ── Step 4: Log outcome back to Snowflake ──────────────────
        pr_url      = heal_result.get('pr_url', 'N/A')
        heal_status = heal_result.get('status', 'unknown')
        summary     = heal_result.get('summary', '')

        session.sql(f"""
            INSERT INTO PIPELINE_RUN_LOG
                (RUN_ID, MODEL_NAME, STATUS, STARTED_AT, FINISHED_AT,
                 ROWS_AFFECTED, ERROR_MESSAGE, TRIGGERED_BY)
            VALUES (
                '{model_name}_heal_' || TO_VARCHAR(CURRENT_TIMESTAMP(), 'YYYYMMDDHH24MISS'),
                '{model_name}',
                '{"success" if heal_status == "fixed" else "failure"}',
                CURRENT_TIMESTAMP(),
                CURRENT_TIMESTAMP(),
                0,
                'Auto-healed by ArcAI. PR: {pr_url}. {summary}',
                'arcai_healer_agent'
            )
        """).collect()

        results.append({
            'model': model_name,
            'diagnosis': diagnosis,
            'heal_status': heal_status,
            'pr_url': pr_url,
            'summary': summary,
        })

    return {
        'status': 'completed',
        'models_processed': len(results),
        'results': results,
        'run_at': str(datetime.now(timezone.utc)),
    }
$$;
