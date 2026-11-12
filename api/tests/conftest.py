"""Tests never touch the hosted database. DB tests use TEST_DATABASE_URL (default: the local
docker Postgres); if that isn't reachable they skip."""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://finn:finn@localhost:5432/finn"
)
