from io import BytesIO, StringIO
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.audit.models import PlatformAuditLog
from apps.tenants.models import Tenant, Membership
from apps.stations.models import Station, StationLogo
from apps.fuel.models import FuelProduct, Tank
from apps.sales.models import FuelSale
from apps.shifts.models import Shift
from apps.operations.services import stock, cash_balance, customer_balance
from apps.customers.models import Customer


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StationBrandingTests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.tenant = Tenant.objects.create(name="Brand Station", slug="brand-station")
        self.other = Tenant.objects.create(name="Other Station", slug="other-brand")
        for tenant in [self.tenant, self.other]:
            Station.all_tenants.create(tenant=tenant, name=tenant.name, phone="private-phone")
        self.owner = get_user_model().objects.create_user(username="brand-owner")
        Membership.all_tenants.create(tenant=self.tenant, user=self.owner, role="owner")
        self.admin = get_user_model().objects.create_superuser(username="brand-admin", password="PrivateTestPassword392!")

    def image(self):
        content = BytesIO()
        Image.new("RGB", (60, 40), "green").save(content, "PNG")
        return SimpleUploadedFile("logo.png", content.getvalue(), content_type="image/png")

    def client_for(self, user, tenant=None, csrf=False):
        client = APIClient(enforce_csrf_checks=csrf)
        client.force_login(user)
        if tenant:
            session = client.session
            session["active_tenant_id"] = str(tenant.pk)
            session.save()
        return client

    def test_owner_brand_is_public_without_exposing_station_data(self):
        response = self.client_for(self.owner, self.tenant).post("/api/v1/station/logo/", {"logo": self.image()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        anonymous = APIClient()
        branding = anonymous.get("/api/v1/branding/brand-station/?tenant_id="+str(self.other.pk))
        self.assertEqual(set(branding.data), {"name", "slug", "primary_color", "logo_url"})
        self.assertEqual(branding.data["name"], self.tenant.name)
        logo = anonymous.get(branding.data["logo_url"])
        self.assertEqual(logo.status_code, 200)
        self.assertTrue(b"".join(logo.streaming_content).startswith(b"\x89PNG"))
        self.assertEqual(anonymous.get("/api/v1/station/").status_code, 403)
        self.assertEqual(anonymous.get("/api/v1/station/logo/").status_code, 403)
        self.assertEqual(anonymous.post("/api/v1/branding/brand-station/logo/", {}).status_code, 405)
        self.assertEqual(anonymous.get("/api/v1/branding/").status_code, 404)

    def test_platform_can_upload_without_station_membership_and_is_audited(self):
        response = self.client_for(self.admin).post(f"/api/v1/platform/tenants/{self.other.pk}/logo/", {"logo": self.image()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.other.refresh_from_db()
        self.tenant.refresh_from_db()
        self.assertTrue(self.other.logo_path.startswith(f"logos/{self.other.pk}/"))
        self.assertEqual(self.tenant.logo_path, "")
        self.assertTrue(PlatformAuditLog.objects.filter(actor=self.admin, action="logo_changed", object_id=str(self.other.pk)).exists())
        self.assertFalse(Membership.all_tenants.filter(user=self.admin).exists())

    def test_owner_cannot_use_platform_upload_or_choose_another_tenant(self):
        client = self.client_for(self.owner, self.tenant)
        self.assertEqual(client.post(f"/api/v1/platform/tenants/{self.other.pk}/logo/", {"logo": self.image()}, format="multipart").status_code, 403)
        self.assertEqual(client.post("/api/v1/station/logo/?tenant_id="+str(self.other.pk), {"logo": self.image()}, format="multipart").status_code, 200)
        self.other.refresh_from_db()
        self.assertEqual(self.other.logo_path, "")

    def test_platform_upload_requires_csrf_and_valid_image(self):
        url = f"/api/v1/platform/tenants/{self.tenant.pk}/logo/"
        self.assertEqual(self.client_for(self.admin, csrf=True).post(url, {"logo": self.image()}, format="multipart").status_code, 403)
        self.assertEqual(self.client_for(self.admin).post(url, {"logo": SimpleUploadedFile("bad.svg", b"<svg/>")}, format="multipart").status_code, 400)

    def test_inactive_and_missing_branding_are_unavailable(self):
        self.tenant.is_active = False
        self.tenant.save()
        anonymous = APIClient()
        for slug in ["brand-station", "missing"]:
            self.assertEqual(anonymous.get(f"/api/v1/branding/{slug}/").status_code, 404)
            self.assertEqual(anonymous.get(f"/api/v1/branding/{slug}/logo/").status_code, 404)

    @override_settings(LOGO_STORAGE="database")
    def test_database_logo_survives_without_a_local_file_and_stays_scoped(self):
        client = self.client_for(self.owner, self.tenant)
        first = client.post("/api/v1/station/logo/", {"logo": self.image()}, format="multipart")
        self.assertEqual(first.status_code, 200, first.data)
        self.tenant.refresh_from_db()
        self.assertEqual(StationLogo.objects.for_tenant(self.tenant).count(), 1)
        self.assertFalse(StationLogo.objects.for_tenant(self.other).exists())
        self.assertFalse((Path(self.media.name) / self.tenant.logo_path).exists())
        response = APIClient().get(first.data["logo_url"])
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        self.assertEqual(client.post("/api/v1/station/logo/", {"logo": self.image()}, format="multipart").status_code, 200)
        self.assertEqual(StationLogo.objects.for_tenant(self.tenant).count(), 1)

    @override_settings(LOGO_STORAGE="database")
    def test_platform_database_upload_has_no_membership_side_effect(self):
        response = self.client_for(self.admin).post(f"/api/v1/platform/tenants/{self.other.pk}/logo/", {"logo": self.image()}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(StationLogo.objects.for_tenant(self.other).exists())
        self.assertFalse(Membership.all_tenants.filter(user=self.admin).exists())

    @override_settings(DEBUG=True)
    def test_sample_data_is_scoped_balanced_and_repeat_safe(self):
        output = StringIO()
        call_command("create_demo_users", stdout=output)
        original_password = self.owner.password
        call_command("seed_demo_data", stdout=output)
        tenant = Tenant.objects.get(slug="development-demo")
        self.assertEqual(FuelProduct.objects.for_tenant(tenant).count(), 2)
        self.assertEqual(FuelSale.objects.for_tenant(tenant).count(), 2)
        self.assertEqual(Shift.objects.for_tenant(tenant).filter(status="open", attendant__user__username="demo-worker").count(), 1)
        self.assertEqual(cash_balance(tenant), Decimal("14550.00"))
        for name, expected in [("Petrol Tank", "6450"), ("Diesel Tank", "6465")]:
            self.assertEqual(stock(tenant, Tank.objects.for_tenant(tenant).get(name=name)), Decimal(expected))
        self.assertEqual(customer_balance(tenant, Customer.objects.for_tenant(tenant).get(code="demo-transport")), Decimal("2100.00"))
        call_command("seed_demo_data", stdout=output)
        self.assertEqual(FuelSale.objects.for_tenant(tenant).count(), 2)
        self.assertFalse(FuelProduct.objects.for_tenant(self.tenant).exists())
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.password, original_password)

    @override_settings(DEBUG=False)
    def test_sample_data_refuses_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo_data", stdout=StringIO())
