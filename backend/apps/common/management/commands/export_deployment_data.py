from django.core.management.base import BaseCommand
from apps.common.deployment_bundle import export_bundle


class Command(BaseCommand):
    help = "Export the current records and logos to a private ZIP (never commit it)."

    def add_arguments(self, parser):
        parser.add_argument("output")

    def handle(self, *args, **options):
        manifest = export_bundle(options["output"])
        self.stdout.write(self.style.SUCCESS(f"Private transfer exported: {sum(manifest['counts'].values())} records, {len(manifest['logos'])} logos; snapshot {manifest['exported_at']}."))
        self.stdout.write("Contains private data and password hashes. Keep outside GitHub and public URLs.")
