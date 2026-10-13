from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.stations.models import Station
from apps.tenants.models import Membership, Tenant

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthAndIsolationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(name="Station A", slug="station-a")
        cls.tenant_b = Tenant.objects.create(name="Station B", slug="station-b")
        cls.owner = User.objects.create_user(username="owner-a", password="test-owner-password-813")
        cls.worker = User.objects.create_user(username="worker-a", password="test-worker-password-813")
        cls.superadmin = User.objects.create_superuser(username="system-admin", password="test-admin-password-813")
        cls.membership = Membership.all_tenants.create(tenant=cls.tenant_a, user=cls.owner, role="owner")
        cls.worker_membership = Membership.all_tenants.create(tenant=cls.tenant_a, user=cls.worker, role="worker")
        cls.station_a = Station.all_tenants.create(tenant=cls.tenant_a, name="Station A", settings={"private_financial_setting": 42})
        cls.station_b = Station.all_tenants.create(tenant=cls.tenant_b, name="Station B")

    def setUp(self):
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)

    def login(self, username="owner-a", password="test-owner-password-813", **extra):
        token = self.client.get("/api/v1/auth/csrf/").json()["csrf_token"]
        return self.client.post("/api/v1/auth/login/", {"username": username, "password": password, **extra}, format="json", HTTP_X_CSRFTOKEN=token)

    def test_login_sets_http_only_session_and_me_returns_identity(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cookies["sessionid"]["httponly"])
        self.assertEqual(self.client.get("/api/v1/auth/me/").json()["user"]["tenant"]["id"], str(self.tenant_a.id))
        self.assertEqual(AuditLog.objects.for_tenant(self.tenant_a).get().action, "login")

    def test_password_is_hashed(self):
        self.assertNotEqual(self.owner.password, "test-owner-password-813")
        self.assertTrue(self.owner.check_password("test-owner-password-813"))

    def test_login_requires_csrf_even_for_anonymous_users(self):
        response = self.client.post("/api/v1/auth/login/", {"username": "owner-a", "password": "test-owner-password-813"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"]["code"], "csrf_failed")

    def test_incorrect_password_has_generic_error(self):
        response = self.login(password="incorrect")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["code"], "invalid_credentials")

    def test_login_rejects_disabled_user(self):
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(self.login().status_code, 401)

    def test_login_rejects_inactive_tenant(self):
        self.tenant_a.is_active = False
        self.tenant_a.save()
        self.assertEqual(self.login().status_code, 403)

    def test_multiple_memberships_require_verified_selection(self):
        Membership.all_tenants.create(tenant=self.tenant_b, user=self.owner, role="owner")
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "unassigned")
        self.assertNotIn("active_tenant_id", self.client.session)

    def test_client_tenant_id_does_not_control_login_context(self):
        response = self.login(tenant_id=str(self.tenant_b.id))
        self.assertEqual(response.json()["user"]["tenant"]["id"], str(self.tenant_a.id))

    def test_client_query_and_header_cannot_access_other_station(self):
        self.login()
        response = self.client.get(f"/api/v1/station/?tenant_id={self.tenant_b.id}", HTTP_X_TENANT_ID=str(self.tenant_b.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(self.station_a.id))
        self.assertNotIn("Station B", response.content.decode())

    def test_server_session_context_is_revalidated_against_membership(self):
        self.login()
        session = self.client.session
        session["active_tenant_id"] = str(self.tenant_b.id)
        session.save()
        self.assertEqual(self.client.get("/api/v1/station/").status_code, 403)

    def test_revoked_membership_denies_existing_session(self):
        self.login()
        self.membership.is_active = False
        self.membership.save()
        self.assertEqual(self.client.get("/api/v1/station/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)

    def test_deactivated_tenant_denies_existing_session(self):
        self.login()
        self.tenant_a.is_active = False
        self.tenant_a.save()
        self.assertEqual(self.client.get("/api/v1/station/").status_code, 403)

    def test_worker_receives_only_safe_station_fields(self):
        login_response = self.login("worker-a", "test-worker-password-813")
        self.assertNotIn("reports.financial", login_response.json()["user"]["permissions"])
        response = self.client.get("/api/v1/station/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("settings", response.json())
        self.assertNotIn("private_financial_setting", response.content.decode())

    def test_permission_override_can_deny_station_read(self):
        self.worker_membership.permission_overrides = {"station.view": False}
        self.worker_membership.save()
        self.login("worker-a", "test-worker-password-813")
        self.assertEqual(self.client.get("/api/v1/station/").status_code, 403)

    def test_superadmin_has_no_implicit_tenant_access(self):
        self.assertEqual(self.login("system-admin", "test-admin-password-813").status_code, 200)
        self.assertIsNone(self.client.get("/api/v1/auth/me/").json()["user"]["tenant"])
        self.assertEqual(self.client.get("/api/v1/station/").status_code, 403)

    def test_anonymous_station_request_is_denied(self):
        self.assertEqual(self.client.get("/api/v1/station/").status_code, 403)

    def test_logout_requires_csrf_and_uses_rotated_login_token(self):
        response = self.login()
        self.assertEqual(self.client.post("/api/v1/auth/logout/").status_code, 403)
        logout = self.client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=response.json()["csrf_token"])
        self.assertEqual(logout.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 403)
        self.assertEqual(list(AuditLog.objects.for_tenant(self.tenant_a).values_list("action", flat=True)), ["logout", "login"])

    def test_logout_still_works_after_membership_revocation(self):
        response = self.login()
        self.membership.is_active = False
        self.membership.save()
        logout = self.client.post("/api/v1/auth/logout/", HTTP_X_CSRFTOKEN=response.json()["csrf_token"])
        self.assertEqual(logout.status_code, 204)

    def test_login_is_rate_limited(self):
        for _ in range(10):
            self.assertEqual(self.login(password="incorrect").status_code, 401)
        self.assertEqual(self.login(password="incorrect").status_code, 429)

    def test_owner_can_update_station_in_phase_two(self):
        response = self.login()
        update = self.client.patch("/api/v1/station/", {"name": "Changed"}, format="json", HTTP_X_CSRFTOKEN=response.json()["csrf_token"])
        self.assertEqual(update.status_code, 200)
