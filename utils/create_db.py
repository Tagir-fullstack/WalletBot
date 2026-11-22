from pathlib import Path


def create_db(connection):
    """Idempotent schema; existing legacy tables are left intact."""
    connection.execute(Path(__file__).with_name('schema.sql').read_text())
