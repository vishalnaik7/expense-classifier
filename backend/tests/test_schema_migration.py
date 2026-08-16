"""
Regression test for _sync_schema(): a database file created before a model
gained a new column must not crash with "no such column" - it should be
auto-migrated (and existing rows preserved) the next time the app starts.
"""
import sqlalchemy

import main as main_module


def test_sync_schema_adds_missing_column_and_preserves_existing_rows(tmp_path):
    db_path = tmp_path / 'stale.db'
    db_url = f'sqlite:///{db_path}'

    stale_engine = sqlalchemy.create_engine(db_url)
    with stale_engine.begin() as conn:
        conn.execute(sqlalchemy.text('''
            CREATE TABLE categories (
                id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                icon VARCHAR(50),
                color VARCHAR(7)
            )
        '''))
        conn.execute(sqlalchemy.text(
            "INSERT INTO categories (id, name, icon, color) VALUES ('cat1', 'Groceries', 'x', '#FF6384')"
        ))

    # Should not raise - the missing `user_id` column gets added in place,
    # entirely against this throwaway engine (no shared app/db state touched).
    main_module._sync_schema(engine=stale_engine)

    with stale_engine.connect() as conn:
        columns = {row[1] for row in conn.execute(sqlalchemy.text("PRAGMA table_info(categories)"))}
        assert 'user_id' in columns

        row = conn.execute(sqlalchemy.text(
            "SELECT name, user_id FROM categories WHERE id = 'cat1'"
        )).fetchone()
        assert row is not None, 'pre-existing row must survive the migration'
        assert row[0] == 'Groceries'
        assert row[1] is None

    stale_engine.dispose()
