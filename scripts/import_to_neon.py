"""One-time private transfer from this workstation to a NEW Neon database."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlparse, parse_qs

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("bundle", type=Path)
arguments = parser.parse_args()
connection_url = getpass("Paste the NEW database's DIRECT Neon connection string (hidden): ").strip()
parsed = urlparse(connection_url)
if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or not parsed.hostname.endswith(".neon.tech") or "-pooler" in parsed.hostname:
    raise SystemExit("Use the direct PostgreSQL connection URL for the new Neon database.")
if parse_qs(parsed.query).get("sslmode", [""])[0] not in {"require", "verify-ca", "verify-full"}:
    raise SystemExit("The Neon connection URL must require TLS.")
if not arguments.bundle.is_file():
    raise SystemExit("The private transfer bundle is missing.")
os.environ.update({"DATABASE_URL": connection_url, "DJANGO_DEBUG": "false", "USE_SQLITE": "false",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "DJANGO_LOGO_STORAGE": "database",
    "DJANGO_CACHE_BACKEND": "database", "DJANGO_CACHE_LOCATION": "petrol_cache", "DJANGO_SETTINGS_MODULE": "config.settings"})
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import django
django.setup()
from django.db import connection
from django.core.management import call_command
from apps.common.deployment_bundle import read_bundle

read_bundle(arguments.bundle)  # Validate locally before making schema changes.
if connection.introspection.table_names():
    raise SystemExit("The Neon database is not empty. Nothing was migrated/imported. Create a separate demo database.")
confirmation = input("This imports private records into the new Neon database. Type IMPORT to continue: ")
if confirmation != "IMPORT":
    raise SystemExit("Import cancelled; no schema/data changes made.")
call_command("migrate", interactive=False)
call_command("createcachetable")
call_command("import_deployment_data", str(arguments.bundle.resolve()), confirm_empty_target=True)
print("Transfer complete. Point Render at this Neon database; local .env and SQLite were not changed.")
