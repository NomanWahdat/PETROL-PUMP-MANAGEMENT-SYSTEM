from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from zipfile import ZipFile, ZIP_DEFLATED

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from apps.common.deployment_bundle import export_bundle, import_bundle, read_bundle
from apps.tenants.models import Tenant
from apps.stations.models import StationLogo
from apps.sales.models import FuelSale
from apps.fuel.models import Tank
from apps.operations.services import stock, cash_balance


@override_settings(DEBUG=True, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeploymentExportTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.media = override_settings(MEDIA_ROOT=Path(self.folder.name)/"media")
        self.media.enable()
        self.addCleanup(self.media.disable)
        call_command("create_demo_users", stdout=StringIO())
        call_command("seed_demo_data", stdout=StringIO())
        self.path = Path(self.folder.name)/"data.zip"

    def test_export_contains_complete_business_records_and_logos_but_no_sessions(self):
        manifest = export_bundle(self.path)
        _, _, records, images = read_bundle(self.path)
        self.assertEqual(manifest["counts"]["accounts.user"], 5)
        self.assertEqual(manifest["counts"]["sales.fuelsale"], 2)
        self.assertEqual(len(images), 1)
        self.assertFalse(any(row["model"].startswith("sessions.") for row in records))
        self.assertEqual(records[0]["model"], "accounts.user")
        self.assertTrue(get_user_model().objects.get(username="demo-superadmin").check_password("PetrolDemo2026!"))

    def test_export_refuses_existing_output_and_tampered_bundle(self):
        export_bundle(self.path)
        with self.assertRaises(CommandError):
            export_bundle(self.path)
        modified = Path(self.folder.name)/"modified.zip"
        with ZipFile(self.path) as source, ZipFile(modified, "w", ZIP_DEFLATED) as target:
            for name in source.namelist():
                target.writestr(name, b"[]" if name == "data.json" else source.read(name))
        with self.assertRaises(CommandError):
            read_bundle(modified)

    def test_import_requires_explicit_confirmation(self):
        export_bundle(self.path)
        with self.assertRaises(CommandError):
            call_command("import_deployment_data", str(self.path), stdout=StringIO())


@skipUnless(connection.vendor == "postgresql", "The deployment import requires PostgreSQL.")
@override_settings(DEBUG=True, LOGO_STORAGE="database", PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DeploymentImportTests(TransactionTestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.override = override_settings(MEDIA_ROOT=Path(self.folder.name)/"media")
        self.override.enable()
        self.addCleanup(self.override.disable)
        call_command("create_demo_users", stdout=StringIO())
        call_command("seed_demo_data", stdout=StringIO())
        self.path = Path(self.folder.name)/"data.zip"
        export_bundle(self.path)

    def test_import_rejects_nonempty_target_without_changing_data(self):
        before = FuelSale.all_tenants.count()
        with self.assertRaises(CommandError):
            import_bundle(self.path, {"demo-superadmin": "NewPrivateAdmin392!"})
        self.assertEqual(FuelSale.all_tenants.count(), before)

    def test_full_roundtrip_preserves_decimals_ids_users_and_logos(self):
        expected_ids = set(FuelSale.all_tenants.values_list("pk", flat=True))
        owner_hash = get_user_model().objects.get(username="demo-owner").password
        call_command("flush", interactive=False, verbosity=0)
        import_bundle(self.path, {"demo-superadmin": "NewPrivateAdmin392!"})
        tenant = Tenant.objects.get(slug="development-demo")
        self.assertEqual(set(FuelSale.all_tenants.values_list("pk", flat=True)), expected_ids)
        self.assertEqual(cash_balance(tenant), Decimal("14550.00"))
        self.assertEqual(stock(tenant, Tank.objects.for_tenant(tenant).get(name="Diesel Tank")), Decimal("6465.000"))
        self.assertEqual(StationLogo.objects.for_tenant(tenant).count(), 1)
        self.assertEqual(get_user_model().objects.get(username="demo-owner").password, owner_hash)
        admin = get_user_model().objects.get(username="demo-superadmin")
        self.assertTrue(admin.check_password("NewPrivateAdmin392!"))
        self.assertFalse(admin.check_password("PetrolDemo2026!"))

    def test_bad_admin_password_rolls_back_entire_import(self):
        call_command("flush", interactive=False, verbosity=0)
        with self.assertRaises(CommandError):
            import_bundle(self.path, {"demo-superadmin": "PetrolDemo2026!"})
        self.assertEqual(get_user_model().objects.count(), 0)
        self.assertEqual(FuelSale.all_tenants.count(), 0)
