# backend/create_tables.py

from sqlalchemy import text

from database import Base, engine
import models  # noqa: F401  - needed so models register with Base


SCHEMA_NAME = "multichat"


def main() -> None:
    # 1. Ensure the schema exists in PostgreSQL
    print(f"Ensuring schema '{SCHEMA_NAME}' exists...")
    with engine.connect() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA_NAME}"'))
        conn.commit()

    # 2. Create all tables defined on Base (User, Class, ClassMember, Message)
    print("Creating tables in schema", SCHEMA_NAME, "...")
    Base.metadata.create_all(bind=engine)
    print("Done.")


if __name__ == "__main__":
    main()
