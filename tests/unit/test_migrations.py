from alembic import command
from sqlalchemy import Engine, inspect

from tests.conftest import alembic_config

EXPECTED_TABLES = {
    "users",
    "retailers",
    "products",
    "price_snapshots",
    "watches",
    "notifications",
    "scrape_runs",
}


def test_downgrade_base_then_upgrade_head(engine: Engine) -> None:
    config = alembic_config(engine.url.render_as_string(hide_password=False))
    engine.dispose()
    try:
        command.downgrade(config, "base")
        assert not EXPECTED_TABLES & set(inspect(engine).get_table_names())
    finally:
        command.upgrade(config, "head")
        engine.dispose()

    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
