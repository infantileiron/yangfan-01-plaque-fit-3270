"""Initial schema for a fresh Compose volume."""
from sqlalchemy import inspect, text

from src.models.account import Account
from src.models.audit import Event
from src.models.dataset import Dataset
from src.models.measurement import Measurement
from src.models.review import Review
from src.models.run import Run

SCHEMA = (Account, Dataset, Run, Review, Event, Measurement)


def migrate(engine):
    tables = [model.__table__ for model in SCHEMA]
    Account.metadata.create_all(engine, tables=tables)
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("runs")}
        if "evidence" not in columns:
            connection.execute(text("ALTER TABLE runs ADD COLUMN evidence JSON"))
