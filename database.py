# backend/database.py

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ====================================================
# Database URL
# ====================================================
# Default: local PostgreSQL database.
# Change the connection string here if you use another DB
# or override with an environment variable DATABASE_URL.
DB_DEFAULT = "postgresql+psycopg2://multichat_user:Helmi123@localhost:5432/multichat"

DATABASE_URL = os.getenv("DATABASE_URL", DB_DEFAULT)

# SQLite needs special connect_args, Postgres/MySQL do not
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()
