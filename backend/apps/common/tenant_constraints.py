"""Migration helpers for same-tenant foreign keys on PostgreSQL and SQLite."""


def add_constraints(schema_editor, links):
    quote = schema_editor.quote_name
    for name, child, columns, parent, targets in links:
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(f"ALTER TABLE {quote(child)} ADD CONSTRAINT {quote(name)} FOREIGN KEY ({', '.join(map(quote, columns))}) REFERENCES {quote(parent)} ({', '.join(map(quote, targets))}) DEFERRABLE INITIALLY DEFERRED")
        elif schema_editor.connection.vendor == "sqlite":
            where = " AND ".join(f"{quote(target)} = NEW.{quote(column)}" for column, target in zip(columns, targets))
            nonnull = " AND ".join(f"NEW.{quote(column)} IS NOT NULL" for column in columns)
            for event in ["INSERT", "UPDATE"]:
                schema_editor.execute(f"CREATE TRIGGER {quote(name + '_' + event.lower())} BEFORE {event} ON {quote(child)} WHEN {nonnull} AND NOT EXISTS (SELECT 1 FROM {quote(parent)} WHERE {where}) BEGIN SELECT RAISE(ABORT, 'Cross-tenant relationship rejected'); END")
            # Also guard parent key changes; SQLite has no ALTER TABLE composite FK.
            references = " AND ".join(f"{quote(column)} = OLD.{quote(target)}" for column, target in zip(columns, targets))
            changed = " OR ".join(f"NEW.{quote(target)} != OLD.{quote(target)}" for target in targets)
            schema_editor.execute(f"CREATE TRIGGER {quote(name + '_parent')} BEFORE UPDATE ON {quote(parent)} WHEN ({changed}) AND EXISTS (SELECT 1 FROM {quote(child)} WHERE {references}) BEGIN SELECT RAISE(ABORT, 'Referenced tenant relationship cannot change'); END")
        else:
            raise RuntimeError("Tenant constraints require PostgreSQL or SQLite.")


def remove_constraints(schema_editor, links):
    quote = schema_editor.quote_name
    for name, child, *_ in links:
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(f"ALTER TABLE {quote(child)} DROP CONSTRAINT {quote(name)}")
        elif schema_editor.connection.vendor == "sqlite":
            for suffix in ["_insert", "_update", "_parent"]:
                schema_editor.execute(f"DROP TRIGGER IF EXISTS {quote(name + suffix)}")
