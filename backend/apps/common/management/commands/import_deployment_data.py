from getpass import getpass
from django.core.management.base import BaseCommand, CommandError
from apps.common.deployment_bundle import read_bundle, import_bundle


class Command(BaseCommand):
    help = "Import a private transfer into fresh PostgreSQL; prompts for private Super Admin passwords."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("--confirm-empty-target", action="store_true")

    def handle(self, *args, **options):
        if not options["confirm_empty_target"]:
            raise CommandError("Use --confirm-empty-target only after verifying the destination is the new deployment database.")
        _, _, records, _ = read_bundle(options["source"])
        usernames = sorted(row["fields"]["username"] for row in records if row["model"] == "accounts.user" and row["fields"]["is_superuser"])
        passwords = {}
        for username in usernames:
            first = getpass(f"New private Super Admin password for {username}: ")
            if first != getpass("Confirm new password: "):
                raise CommandError("Passwords did not match. No records were imported.")
            passwords[username] = first
        manifest = import_bundle(options["source"], passwords)
        self.stdout.write(self.style.SUCCESS(f"Imported {sum(manifest['counts'].values())} original records and {len(manifest['logos'])} logos. Platform passwords rotated; all other account hashes preserved."))
