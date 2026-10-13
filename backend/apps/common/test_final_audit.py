from io import StringIO
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.tenants.models import Tenant, Membership
from apps.tenants.permissions import lock_tenant_access
from apps.stations.models import Station
from apps.fuel.models import FuelProduct
from apps.audit.models import AuditLog


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinalSecurityAuditTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Audit", slug="audit")
        Station.all_tenants.create(tenant=self.tenant, name="Audit")
        self.user = get_user_model().objects.create_user(username="audit-owner", password="AuditPassword392!")
        self.member = Membership.all_tenants.create(tenant=self.tenant, user=self.user, role="owner")
        self.client = APIClient()
        self.client.force_login(self.user)
        session = self.client.session
        session["active_tenant_id"] = str(self.tenant.pk)
        session.save()

    def test_configuration_rechecks_permissions_after_lock_wait(self):
        def revoke_then_lock(request, permission):
            Membership.objects.for_tenant(self.tenant).filter(pk=self.member.pk).update(permission_overrides={"fuel.manage": False})
            return lock_tenant_access(request, permission)
        with patch("apps.common.api.lock_tenant_access", side_effect=revoke_then_lock):
            response = self.client.post("/api/v1/fuel/products/", {"name": "Fuel", "code": "fuel"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FuelProduct.objects.for_tenant(self.tenant).exists())
        self.assertFalse(AuditLog.objects.for_tenant(self.tenant).filter(action="created").exists())

    def test_station_rechecks_revoked_membership_after_lock_wait(self):
        def revoke_then_lock(request, permission):
            Membership.objects.for_tenant(self.tenant).filter(pk=self.member.pk).update(is_active=False)
            return lock_tenant_access(request, permission)
        with patch("apps.stations.views.lock_tenant_access", side_effect=revoke_then_lock):
            response = self.client.patch("/api/v1/station/", {"name": "Unauthorized rename"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Station.objects.for_tenant(self.tenant).get().name, "Audit")

    def test_inactive_global_identity_cannot_keep_writing_with_stale_request(self):
        def disable_then_lock(request, permission):
            get_user_model().objects.filter(pk=self.user.pk).update(is_active=False)
            return lock_tenant_access(request, permission)
        with patch("apps.common.api.lock_tenant_access", side_effect=disable_then_lock):
            response = self.client.post("/api/v1/fuel/products/", {"name": "Fuel", "code": "fuel"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FuelProduct.objects.for_tenant(self.tenant).exists())

    def test_configuration_decimal_inputs_reject_floats(self):
        response = self.client.post("/api/v1/fuel/products/", {"name": "Fuel", "code": "fuel", "selling_price": 73.4567}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch("/api/v1/station/", {"settings": {"tax_rate": 2.5}}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FuelProduct.objects.for_tenant(self.tenant).exists())

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=128)
    def test_oversized_json_is_rejected_with_safe_structured_error(self):
        response = self.client.post("/api/v1/fuel/products/", {"name": "Fuel", "code": "fuel", "notes": "x"*500}, format="json")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data["error"]["code"], "payload_too_large")
        self.assertFalse(FuelProduct.objects.for_tenant(self.tenant).exists())

    def test_forged_forwarded_ip_does_not_bypass_direct_login_throttle(self):
        cache.clear()
        anonymous = APIClient()
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}):
            for index in range(10):
                response = anonymous.post("/api/v1/auth/login/", {"username": "missing", "password": "invalid"}, format="json", HTTP_X_FORWARDED_FOR=f"198.51.100.{index}", REMOTE_ADDR="192.0.2.120")
                self.assertEqual(response.status_code, 401)
            response = anonymous.post("/api/v1/auth/login/", {"username": "missing", "password": "invalid"}, format="json", HTTP_X_FORWARDED_FOR="198.51.100.100", REMOTE_ADDR="192.0.2.120")
            self.assertEqual(response.status_code, 429)
        cache.clear()


@override_settings(DEBUG=True, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DevelopmentAccountsTests(TestCase):
    def test_demo_accounts_are_isolated_and_never_overwrite_existing_data(self):
        existing = Tenant.objects.create(name="Existing", slug="existing")
        call_command("create_demo_users", stdout=StringIO())
        User = get_user_model()
        self.assertTrue(User.objects.get(username="demo-worker").check_password("PetrolDemo2026!"))
        demo = Tenant.objects.get(slug="development-demo")
        self.assertEqual(Membership.objects.for_tenant(demo).count(), 4)
        self.assertTrue(User.objects.get(username="demo-superadmin").is_superuser)
        self.assertTrue(Tenant.objects.filter(pk=existing.pk, name="Existing").exists())
        with self.assertRaises(CommandError):
            call_command("create_demo_users", stdout=StringIO())
        self.assertEqual(User.objects.count(), 5)

    @override_settings(DEBUG=False)
    def test_demo_command_is_disabled_in_production(self):
        with self.assertRaises(CommandError):
            call_command("create_demo_users", stdout=StringIO())
        self.assertFalse(Tenant.objects.exists())
