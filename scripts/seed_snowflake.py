"""
Seed Snowflake with synthetic data for the pipeline healer demo.
Creates: DEMOP.DBT_PIPELINE.RAW_ORDERS, RAW_CUSTOMERS, RAW_PRODUCTS
"""
import sys, os
from pathlib import Path

# Auto-detect and switch to .venv python if running under global python
_venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python3"
if _venv_python.exists() and sys.executable != str(_venv_python):
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)

import random, uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
import snowflake.connector

load_dotenv()

conn = snowflake.connector.connect(
    account=os.environ["SNOWFLAKE_ACCOUNT"],
    user=os.environ["SNOWFLAKE_USER"],
    password=os.environ["SNOWFLAKE_PASSWORD"],
    role=os.environ["SNOWFLAKE_ROLE"],
    warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
    database=os.environ["SNOWFLAKE_DATABASE"],
)
cur = conn.cursor()

print("Setting up schema...")
cur.execute("CREATE SCHEMA IF NOT EXISTS DBT_PIPELINE")
cur.execute("USE SCHEMA DBT_PIPELINE")

# ── RAW_PRODUCTS ───────────────────────────────────────────────────
cur.execute("""
CREATE OR REPLACE TABLE RAW_PRODUCTS (
    PRODUCT_ID      VARCHAR(36) PRIMARY KEY,
    PRODUCT_NAME    VARCHAR(100),
    CATEGORY        VARCHAR(50),
    UNIT_PRICE      FLOAT,
    IS_ACTIVE       BOOLEAN
)
""")

products = [
    ("PRD001", "Enterprise License",   "Software",  4999.00, True),
    ("PRD002", "Pro License",          "Software",  1299.00, True),
    ("PRD003", "Support Package",      "Services",   499.00, True),
    ("PRD004", "Implementation",       "Services",  2500.00, True),
    ("PRD005", "Training Bundle",      "Training",   799.00, True),
    ("PRD006", "API Access",           "Platform",   199.00, True),
    ("PRD007", "Data Connector",       "Platform",   349.00, True),
    ("PRD008", "Legacy Module",        "Software",   299.00, False),
]
cur.executemany(
    "INSERT INTO RAW_PRODUCTS VALUES (%s,%s,%s,%s,%s)",
    products
)
print(f"  Inserted {len(products)} products")

# ── RAW_CUSTOMERS ──────────────────────────────────────────────────
cur.execute("""
CREATE OR REPLACE TABLE RAW_CUSTOMERS (
    CUSTOMER_ID     VARCHAR(36) PRIMARY KEY,
    CUSTOMER_NAME   VARCHAR(100),
    EMAIL           VARCHAR(100),
    SEGMENT         VARCHAR(20),
    REGION          VARCHAR(20),
    CREATED_AT      TIMESTAMP_NTZ
)
""")

segments = ["Enterprise", "Mid-Market", "SMB"]
regions  = ["APAC", "EMEA", "AMER", "LATAM"]
customers = []
for i in range(1, 51):
    cid = f"CUST{i:04d}"
    customers.append((
        cid,
        f"Company {i}",
        f"contact{i}@company{i}.com",
        random.choice(segments),
        random.choice(regions),
        datetime(2023, 1, 1) + timedelta(days=random.randint(0, 365)),
    ))
cur.executemany(
    "INSERT INTO RAW_CUSTOMERS VALUES (%s,%s,%s,%s,%s,%s)",
    customers
)
print(f"  Inserted {len(customers)} customers")

# ── RAW_ORDERS ─────────────────────────────────────────────────────
cur.execute("""
CREATE OR REPLACE TABLE RAW_ORDERS (
    ORDER_ID            VARCHAR(36) PRIMARY KEY,
    CUSTOMER_ID         VARCHAR(36),
    ORDER_DATE          DATE,
    STATUS              VARCHAR(20),
    AMOUNT              FLOAT,
    REGION              VARCHAR(20),
    PRODUCT_CATEGORY    VARCHAR(50),
    PRODUCT_ID          VARCHAR(36),
    CREATED_AT          TIMESTAMP_NTZ
)
""")

statuses   = ["completed", "completed", "completed", "pending", "refunded"]
categories = ["Software", "Services", "Training", "Platform"]
orders = []
base_date = datetime(2024, 1, 1)
for i in range(1, 501):
    cust = random.choice(customers)
    prod = random.choice(products)
    orders.append((
        f"ORD{i:05d}",
        cust[0],
        (base_date + timedelta(days=random.randint(0, 364))).date(),
        random.choice(statuses),
        round(prod[3] * random.uniform(0.8, 1.2), 2),
        cust[4],
        prod[2],
        prod[0],
        datetime.now(),
    ))
cur.executemany(
    "INSERT INTO RAW_ORDERS VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
    orders
)
print(f"  Inserted {len(orders)} orders")

# ── PIPELINE_RUN_LOG ───────────────────────────────────────────────
# This table tracks dbt run history — the Inspector Agent reads it
cur.execute("""
CREATE OR REPLACE TABLE PIPELINE_RUN_LOG (
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
print("  Created PIPELINE_RUN_LOG table")

conn.commit()
cur.close()
conn.close()
print("\nSeed complete. Snowflake is ready.")
