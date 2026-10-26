
"""Database connectivity checks."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from bizora.db.session import get_engine


def check_database_connection() -> bool:
    """Return whether the database can execute a simple query."""
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
