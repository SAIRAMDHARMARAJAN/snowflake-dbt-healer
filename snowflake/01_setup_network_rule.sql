-- Step 1: Allow Snowflake to call external URLs (ArcAI A2A endpoints)
-- Run this once as ACCOUNTADMIN

USE ROLE ACCOUNTADMIN;
USE DATABASE DEMOP;
USE SCHEMA DBT_PIPELINE;

-- Network rule: allow outbound calls to ArcAI platform
CREATE OR REPLACE NETWORK RULE arcai_network_rule
    MODE = EGRESS
    TYPE = HOST_PORT
    VALUE_LIST = (
        'localhost:8300',       -- local dev ArcAI Studio
        'app.growtharc.com'     -- replace with your production ArcAI host
    );

-- Secret: ArcAI API key stored securely in Snowflake
-- Replace <YOUR_ARCAI_API_KEY> with the key from ArcAI Studio → Settings → API Keys
CREATE OR REPLACE SECRET arcai_api_key
    TYPE = GENERIC_STRING
    SECRET_STRING = '<YOUR_ARCAI_API_KEY>';

-- External access integration: ties network rule + secret together
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION arcai_access_integration
    ALLOWED_NETWORK_RULES = (arcai_network_rule)
    ALLOWED_AUTHENTICATION_SECRETS = (arcai_api_key)
    ENABLED = TRUE;
