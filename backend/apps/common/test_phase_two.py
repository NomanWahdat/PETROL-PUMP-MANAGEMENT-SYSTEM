from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.audit.models import AuditLog, PlatformAuditLog
from apps.employees.models import Employee
from apps.fuel.models import FuelProduct, FuelPriceHistory, Tank, Pump, Nozzle
from apps.stations.models import Station
from apps.tenants.models import Tenant, Membership, RolePolicy

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PhaseTwoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Tenant.objects.create(name="A", slug="a")
        cls.b = Tenant.objects.create(name="B", slug="b")
        cls.station = Station.all_tenants.create(tenant=cls.a, name="A")
        Station.all_tenants.create(tenant=cls.b, name="B")
        cls.users, cls.members = {}, {}
        for role in ["owner", "manager", "worker", "accountant"]:
            user = User.objects.create_user(username=role, password="A-valid-password-921!")
            membership = Membership.all_tenants.create(tenant=cls.a, user=user, role=role)
            Employee.all_tenants.create(tenant=cls.a, membership=membership, name=role)
            cls.users[role], cls.members[role] = user, membership
        cls.admin = User.objects.create_superuser(username="platform", password="A-valid-password-921!")
        cls.other = User.objects.create_user(username="other", password="A-valid-password-921!")
        membership = Membership.all_tenants.create(tenant=cls.b, user=cls.other, role="owner")
        cls.other_employee = Employee.all_tenants.create(tenant=cls.b, membership=membership, name="Private B Employee")
        cls.product = FuelProduct.all_tenants.create(tenant=cls.a, name="Petrol", code="petrol", selling_price="70.1250")
        cls.other_product = FuelProduct.all_tenants.create(tenant=cls.b, name="Private B Fuel", code="petrol")
        cls.tank = Tank.all_tenants.create(tenant=cls.a, name="Tank A", product=cls.product, capacity=1000)
        cls.other_tank = Tank.all_tenants.create(tenant=cls.b, name="Private B Tank", product=cls.other_product, capacity=1000)
        cls.pump = Pump.all_tenants.create(tenant=cls.a, name="Pump A", number="1")
        cls.other_pump = Pump.all_tenants.create(tenant=cls.b, name="Private B Pump", number="1")
        cls.other_nozzle = Nozzle.all_tenants.create(tenant=cls.b, number="1", pump=cls.other_pump, product=cls.other_product, tank=cls.other_tank)
        cls.other_price = FuelPriceHistory.all_tenants.create(tenant=cls.b, product=cls.other_product, purchase_price=0, selling_price=1)

    def client_for(self, role="owner"):
        client = APIClient()
        client.force_login(self.admin if role == "platform" else self.users[role])
        session = client.session
        if role != "platform":
            session["active_tenant_id"] = str(self.a.pk)
        session.save()
        return client

    def test_lists_and_details_are_scoped_for_every_module(self):
        client = self.client_for()
        for path, record in [("employees", self.other_employee), ("fuel/products", self.other_product), ("tanks", self.other_tank), ("pumps", self.other_pump), ("nozzles", self.other_nozzle), ("fuel/price-history", self.other_price)]:
            with self.subTest(path=path):
                response = client.get(f"/api/v1/{path}/?tenant_id={self.b.pk}", HTTP_X_TENANT_ID=str(self.b.pk))
                self.assertEqual(response.status_code, 200)
                self.assertNotIn(str(record.pk), response.content.decode())
                self.assertEqual(client.get(f"/api/v1/{path}/{record.pk}/").status_code, 404)
                self.assertIn(client.patch(f"/api/v1/{path}/{record.pk}/", {"is_active": False}, format="json").status_code, [404, 405])

    def test_worker_cannot_access_configuration_or_platform(self):
        client = self.client_for("worker")
        for path in ["employees", "roles", "fuel/products", "tanks", "pumps", "nozzles", "platform/tenants", "platform/users", "platform/status", "platform/audit", "station/compliance"]:
            with self.subTest(path=path):
                self.assertEqual(client.get(f"/api/v1/{path}/").status_code, 403)
        self.assertEqual(client.patch("/api/v1/station/", {"name": "Wrong"}, format="json").status_code, 403)

    def test_accountant_has_read_only_fuel_access(self):
        client = self.client_for("accountant")
        self.assertEqual(client.get("/api/v1/fuel/products/").status_code, 200)
        self.assertEqual(client.post("/api/v1/fuel/products/", {"name": "X", "code": "x"}, format="json").status_code, 403)
        self.assertEqual(client.get("/api/v1/employees/").status_code, 403)

    def test_manager_creates_workers_but_cannot_escalate_access(self):
        client = self.client_for("manager")
        payload = {"name": "Worker Two", "username": "worker-two", "password": "A-valid-password-922!", "role": "worker"}
        response = client.post("/api/v1/employees/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertNotIn("password", response.data)
        payload.update(username="new-owner", role="owner")
        self.assertEqual(client.post("/api/v1/employees/", payload, format="json").status_code, 400)
        employee = Employee.objects.for_tenant(self.a).get(membership=self.members["owner"])
        self.assertEqual(client.patch(f"/api/v1/employees/{employee.pk}/", {"phone": "123"}, format="json").status_code, 400)

    def test_owner_can_create_each_station_role(self):
        for role in ["owner", "manager", "worker", "accountant"]:
            response = self.client_for().post("/api/v1/employees/", {"name": role, "username": "new-" + role, "password": "A-valid-password-922!", "role": role, "tenant_id": str(self.b.pk)}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            employee = Employee.objects.for_tenant(self.a).get(pk=response.data["id"])
            self.assertEqual(employee.membership.tenant_id, self.a.pk)
            self.assertFalse(employee.membership.user.is_superuser)

    def test_employee_deactivation_revokes_existing_session(self):
        worker_client = self.client_for("worker")
        employee = Employee.objects.for_tenant(self.a).get(membership=self.members["worker"])
        response = self.client_for().patch(f"/api/v1/employees/{employee.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(worker_client.get("/api/v1/station/").status_code, 403)
        self.assertTrue(User.objects.get(pk=self.users["worker"].pk).is_active)

    def test_owner_cannot_revoke_own_access(self):
        employee = Employee.objects.for_tenant(self.a).get(membership=self.members["owner"])
        self.assertEqual(self.client_for().patch(f"/api/v1/employees/{employee.pk}/", {"role": "worker"}, format="json").status_code, 400)

    def test_password_reset_cannot_affect_shared_identity(self):
        Membership.all_tenants.create(tenant=self.b, user=self.users["worker"], role="worker")
        employee = Employee.objects.for_tenant(self.a).get(membership=self.members["worker"])
        response = self.client_for().patch(f"/api/v1/employees/{employee.pk}/", {"password": "A-valid-new-password-922!"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_role_configuration_is_tenant_scoped_and_immediate(self):
        client = self.client_for()
        response = client.post("/api/v1/roles/", {"role": "manager", "permissions": ["station.view"]}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client_for("manager").get("/api/v1/fuel/products/").status_code, 403)
        self.assertEqual(RolePolicy.objects.for_tenant(self.b).count(), 0)

    def test_role_configuration_rejects_system_permissions_and_owner_lockout(self):
        client = self.client_for()
        self.assertEqual(client.post("/api/v1/roles/", {"role": "worker", "permissions": ["system.admin"]}, format="json").status_code, 400)
        self.assertEqual(client.post("/api/v1/roles/", {"role": "owner", "permissions": []}, format="json").status_code, 400)
        self.assertEqual(self.client_for("manager").get("/api/v1/roles/").status_code, 403)

    def test_platform_creates_tenant_station_and_owner_atomically(self):
        response = self.client_for("platform").post("/api/v1/platform/tenants/", {"name": "New", "slug": "new", "owner_name": "Ahmad", "owner_username": "ahmad", "owner_password": "A-valid-password-922!", "language": "ps"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        tenant = Tenant.objects.get(pk=response.data["id"])
        self.assertEqual(Station.objects.for_tenant(tenant).get().language, "ps")
        self.assertEqual(Employee.objects.for_tenant(tenant).count(), 1)
        self.assertNotIn("owner_password", response.data)
        self.assertEqual(PlatformAuditLog.objects.count(), 1)

    def test_platform_rejects_weak_tenant_owner_password_without_partial_data(self):
        response = self.client_for("platform").post("/api/v1/platform/tenants/", {"name": "New", "slug": "new", "owner_name": "Ahmad", "owner_username": "ahmad", "owner_password": "123"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Tenant.objects.filter(slug="new").exists())

    def test_owner_cannot_use_platform_endpoints(self):
        self.assertEqual(self.client_for().post("/api/v1/platform/tenants/", {}, format="json").status_code, 403)
        self.assertEqual(self.client_for().get("/api/v1/platform/users/").status_code, 403)

    def test_platform_deactivation_blocks_existing_station_session(self):
        client = self.client_for()
        response = self.client_for("platform").patch(f"/api/v1/platform/tenants/{self.a.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(client.get("/api/v1/station/").status_code, 403)

    def test_platform_cannot_revoke_own_system_access(self):
        self.assertEqual(self.client_for("platform").patch(f"/api/v1/platform/users/{self.admin.pk}/", {"is_superuser": False}, format="json").status_code, 400)

    def test_tenant_switch_validates_membership_and_rotates_session(self):
        client = self.client_for()
        before = client.session.session_key
        self.assertEqual(client.post("/api/v1/auth/select-tenant/", {"tenant_id": str(self.b.pk)}, format="json").status_code, 403)
        Membership.all_tenants.create(tenant=self.b, user=self.users["owner"], role="manager")
        response = client.post("/api/v1/auth/select-tenant/", {"tenant_id": str(self.b.pk)}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(client.session.session_key, before)
        self.assertEqual(client.get("/api/v1/station/").data["name"], "B")
        self.assertEqual(len(client.get("/api/v1/auth/memberships/").data["results"]), 2)

    def test_password_change_preserves_current_session_and_expires_others(self):
        client = self.client_for()
        other = self.client_for()
        response = client.post("/api/v1/auth/password/", {"current_password": "A-valid-password-921!", "new_password": "A-valid-new-password-922!"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 403)
        self.assertNotIn("password", str(list(AuditLog.objects.for_tenant(self.a).values_list("changes", flat=True))))

    def test_station_profile_branding_and_settings_update(self):
        response = self.client_for().patch("/api/v1/station/", {"name": "Ahmad Station", "primary_color": "#113355", "language": "ps", "settings": {"payment_methods": ["cash", "bank"], "tax_rate": "2.1250", "opening_time": "07:00"}}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.a.refresh_from_db()
        self.assertEqual(self.a.name, "Ahmad Station")
        self.assertEqual(self.a.primary_color, "#113355")
        self.assertEqual(response.data["settings"]["tax_rate"], "2.1250")
        worker_data = self.client_for("worker").get("/api/v1/station/").data
        self.assertNotIn("settings", worker_data)

    def test_station_rejects_invalid_color_timezone_and_configuration(self):
        for payload in [{"primary_color": "javascript:x"}, {"timezone": "not-a-timezone"}, {"settings": {"tax_rate": "-1"}}, {"settings": {"unknown": True}}]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client_for().patch("/api/v1/station/", payload, format="json").status_code, 400)

    def test_fuel_price_history_is_exact_and_read_only(self):
        client = self.client_for()
        response = client.post("/api/v1/fuel/products/", {"name": "Diesel", "code": "diesel", "selling_price": "71.1234", "purchase_price": "60.0001"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        product_id = response.data["id"]
        response = client.patch(f"/api/v1/fuel/products/{product_id}/", {"selling_price": "72.5678", "price_reason": "Supplier price change"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        records = FuelPriceHistory.objects.for_tenant(self.a).filter(product_id=product_id)
        self.assertEqual(records.count(), 2)
        self.assertEqual(records.first().selling_price, Decimal("72.5678"))
        client.patch(f"/api/v1/fuel/products/{product_id}/", {"notes": "No price change"}, format="json")
        self.assertEqual(records.count(), 2)
        self.assertEqual(client.patch(f"/api/v1/fuel/price-history/{records.first().pk}/", {"selling_price": "0"}, format="json").status_code, 405)

    def test_negative_prices_and_duplicate_tenant_codes_are_rejected(self):
        client = self.client_for()
        self.assertEqual(client.post("/api/v1/fuel/products/", {"name": "X", "code": "x", "selling_price": "-1"}, format="json").status_code, 400)
        self.assertEqual(client.post("/api/v1/fuel/products/", {"name": "X", "code": "petrol"}, format="json").status_code, 400)

    def test_cross_tenant_equipment_relations_are_rejected_by_api(self):
        client = self.client_for()
        self.assertEqual(client.post("/api/v1/tanks/", {"name": "Bad", "capacity": "100", "product": str(self.other_product.pk)}, format="json").status_code, 400)
        for field, other in [("pump", self.other_pump), ("product", self.other_product), ("tank", self.other_tank)]:
            payload = {"number": "2", "pump": str(self.pump.pk), "product": str(self.product.pk), "tank": str(self.tank.pk), field: str(other.pk)}
            self.assertEqual(client.post("/api/v1/nozzles/", payload, format="json").status_code, 400)

    def test_cross_tenant_relations_are_rejected_by_database_without_model_validation(self):
        factories = [
            lambda: Tank.all_tenants.create(tenant=self.a, name="Bad", product=self.other_product, capacity=100),
            lambda: FuelPriceHistory.all_tenants.create(tenant=self.a, product=self.other_product, purchase_price=0, selling_price=1),
            lambda: Nozzle.all_tenants.create(tenant=self.a, number="bad", pump=self.other_pump, product=self.product),
            lambda: Nozzle.all_tenants.create(tenant=self.a, number="bad", pump=self.pump, product=self.product, tank=self.other_tank),
            lambda: Employee.all_tenants.create(tenant=self.b, membership=self.members["worker"], name="Bad"),
        ]
        for factory in factories:
            with self.assertRaises(IntegrityError), transaction.atomic():
                factory()
                connection.check_constraints()

    def test_tank_capacity_and_nozzle_fuel_consistency(self):
        client = self.client_for()
        self.assertEqual(client.post("/api/v1/tanks/", {"name": "Bad", "product": str(self.product.pk), "capacity": "100", "opening_quantity": "101"}, format="json").status_code, 400)
        diesel = FuelProduct.all_tenants.create(tenant=self.a, name="Diesel", code="diesel")
        payload = {"number": "2", "pump": str(self.pump.pk), "product": str(diesel.pk), "tank": str(self.tank.pk)}
        self.assertEqual(client.post("/api/v1/nozzles/", payload, format="json").status_code, 400)

    def test_nozzle_initial_reading_cannot_be_silently_rewritten(self):
        client = self.client_for()
        response = client.post("/api/v1/nozzles/", {"number": "2", "pump": str(self.pump.pk), "product": str(self.product.pk), "opening_meter": "123.456"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(client.patch(f"/api/v1/nozzles/{response.data['id']}/", {"opening_meter": "0"}, format="json").status_code, 400)

    def test_records_are_deactivated_not_deleted(self):
        client = self.client_for()
        self.assertEqual(client.delete(f"/api/v1/fuel/products/{self.product.pk}/").status_code, 405)
        response = client.patch(f"/api/v1/pumps/{self.pump.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Pump.objects.for_tenant(self.a).filter(pk=self.pump.pk).exists())

    def test_logo_validation_reencoding_and_isolation(self):
        with TemporaryDirectory() as media, override_settings(MEDIA_ROOT=media):
            client = self.client_for()
            invalid = SimpleUploadedFile("fake.png", b"<html>bad</html>", content_type="image/png")
            self.assertEqual(client.post("/api/v1/station/logo/", {"logo": invalid}, format="multipart").status_code, 400)
            output = BytesIO()
            Image.new("RGB", (20, 20), "red").save(output, format="PNG")
            image = SimpleUploadedFile("logo.png", output.getvalue() + b"<script>bad</script>", content_type="image/png")
            self.assertEqual(client.post("/api/v1/station/logo/", {"logo": image}, format="multipart").status_code, 200)
            response = self.client_for("worker").get("/api/v1/station/logo/")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b"<script>", b"".join(response.streaming_content))
            self.assertEqual(self.client_for("worker").post("/api/v1/station/logo/", {}, format="multipart").status_code, 403)
            second = client.get("/api/v1/station/logo/?tenant_id=" + str(self.b.pk))
            self.assertEqual(second.status_code, 200)
            b"".join(second.streaming_content)
            self.b.refresh_from_db()
            self.assertEqual(self.b.logo_path, "")

    def test_search_and_pagination(self):
        response = self.client_for().get("/api/v1/fuel/products/?search=Petrol&page_size=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(len(response.data["results"]), 1)

    def test_platform_assigns_existing_identity_to_another_tenant(self):
        client = self.client_for("platform")
        response = client.post(f"/api/v1/platform/users/{self.users['worker'].pk}/memberships/", {"tenant_id": str(self.b.pk), "role": "worker"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Membership.objects.for_tenant(self.b).filter(user=self.users["worker"]).count(), 1)
        self.assertEqual(len(client.get(f"/api/v1/platform/users/{self.users['worker'].pk}/memberships/").data["results"]), 2)
        self.assertEqual(self.client_for().post(f"/api/v1/platform/users/{self.users['worker'].pk}/memberships/", {"tenant_id": str(self.b.pk), "role": "owner"}, format="json").status_code, 403)

    def test_platform_membership_update_preserves_last_owner(self):
        response = self.client_for("platform").post(f"/api/v1/platform/users/{self.users['owner'].pk}/memberships/", {"tenant_id": str(self.a.pk), "role": "worker"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_platform_global_disable_preserves_last_station_owner(self):
        response = self.client_for("platform").patch(f"/api/v1/platform/users/{self.users['owner'].pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_platform_can_create_system_and_station_users(self):
        client = self.client_for("platform")
        for payload in [
            {"username": "new-system-admin", "is_superuser": True, "tenant_id": None},
            {"username": "new-station-worker", "is_superuser": False, "tenant_id": str(self.b.pk), "role": "worker"},
        ]:
            response = client.post("/api/v1/platform/users/", {**payload, "password": "A-valid-password-935!"}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertNotIn("password", response.data)

    def test_manager_cannot_clear_individual_denials(self):
        self.members["worker"].permission_overrides = {"station.view": False}
        self.members["worker"].save()
        employee = Employee.objects.for_tenant(self.a).get(membership=self.members["worker"])
        response = self.client_for("manager").patch(f"/api/v1/employees/{employee.pk}/", {"permission_overrides": {}}, format="json")
        self.assertEqual(response.status_code, 400)
