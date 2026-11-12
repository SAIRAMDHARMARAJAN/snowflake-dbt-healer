-- Step 3: Snowflake Task — runs HEAL_PIPELINE on schedule
-- Replace the A2A URLs with the ones you get from ArcAI Studio

USE ROLE ACCOUNTADMIN;
USE DATABASE DEMOP;
USE SCHEMA DBT_PIPELINE;

-- ── The Task ──────────────────────────────────────────────────────
CREATE OR REPLACE TASK PIPELINE_HEALER_TASK
    WAREHOUSE = DG_WH
    SCHEDULE  = 'USING CRON 0 * * * * UTC'   -- every hour; change to '0 6 * * *' for daily 6am
    COMMENT   = 'ArcAI Pipeline Healer — detects failed dbt models and heals via A2A agents'
AS
    CALL HEAL_PIPELINE(
        'https://arcai-stage.solutions.growtharc.com/api/v1/agents/ed5913cb-2e8c-423b-bd8c-082419443ba0',
        'https://arcai-stage.solutions.growtharc.com/api/v1/agents/f2e4d2f2-dc31-4a8a-9be0-db8cfde41d5f',
        24
    );

-- Activate the task (tasks start SUSPENDED by default)
ALTER TASK PIPELINE_HEALER_TASK RESUME;

-- ── Verify setup ──────────────────────────────────────────────────
SHOW TASKS LIKE 'PIPELINE_HEALER_TASK';

-- ── Manual trigger (use this during demo) ─────────────────────────
-- EXECUTE TASK PIPELINE_HEALER_TASK;

-- ── Check task run history ────────────────────────────────────────
-- SELECT *
-- FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
--     SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP()),
--     TASK_NAME => 'PIPELINE_HEALER_TASK'
-- ));
