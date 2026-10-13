"""Real concurrent posting checks, run against PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient
from apps.tenants.models import Tenant, Membership
from apps.stations.models import Station
from apps.fuel.models import FuelProduct, Tank, Pump, Nozzle
from apps.sales.models import FuelSale
from apps.inventory.models import InventoryMovement
from apps.shifts.models import Shift
from apps.cash.models import DailyClosing, CashMovement


@skipUnless(connection.vendor == "postgresql", "Row-lock concurrency requires PostgreSQL.")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrentPostingTests(TransactionTestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Concurrent", slug="concurrent")
        Station.all_tenants.create(tenant=self.tenant, name="Concurrent")
        self.worker = get_user_model().objects.create_user(username="concurrent-worker")
        self.member = Membership.all_tenants.create(tenant=self.tenant, user=self.worker, role="worker")
        product = FuelProduct.all_tenants.create(tenant=self.tenant, name="Fuel", code="fuel", selling_price=70)
        tank = Tank.all_tenants.create(tenant=self.tenant, name="Tank", product=product, capacity=1000, opening_quantity=500)
        pump = Pump.all_tenants.create(tenant=self.tenant, name="Pump", number="1")
        self.nozzle = Nozzle.all_tenants.create(tenant=self.tenant, pump=pump, product=product, tank=tank, number="1", opening_meter=100)

    def api_client(self):
        client = APIClient()
        client.force_login(self.worker)
        session = client.session
        session["active_tenant_id"] = str(self.tenant.pk)
        session.save()
        return client

    def start(self):
        response = self.api_client().post("/api/v1/shifts/", {"nozzle_ids": [str(self.nozzle.pk)]}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data["assignments"][0]["id"]

    def concurrent_posts(self, path, payload, same_key):
        gate = Barrier(2)
        shared_key = uuid4()
        def submit():
            try:
                client = self.api_client()
                gate.wait(timeout=20)
                response = client.post(path, payload, format="json", HTTP_IDEMPOTENCY_KEY=str(shared_key if same_key else uuid4()))
                return response.status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit) for _ in range(2)]
            return sorted(future.result(timeout=30) for future in futures)

    def test_simultaneous_duplicate_key_posts_one_sale(self):
        assignment = self.start()
        self.assertEqual(self.concurrent_posts("/api/v1/sales/", {"assignment_id": assignment, "closing_meter": "110.000"}, True), [200, 200])
        self.assertEqual(FuelSale.objects.for_tenant(self.tenant).count(), 1)
        self.assertEqual(InventoryMovement.objects.for_tenant(self.tenant).count(), 1)

    def test_simultaneous_different_keys_cannot_sell_same_meter_interval_twice(self):
        assignment = self.start()
        self.assertEqual(self.concurrent_posts("/api/v1/sales/", {"assignment_id": assignment, "closing_meter": "110.000"}, False), [200, 400])
        self.assertEqual(FuelSale.objects.for_tenant(self.tenant).count(), 1)

    def test_simultaneous_shift_start_has_one_assignment(self):
        self.assertEqual(self.concurrent_posts("/api/v1/shifts/", {"nozzle_ids": [str(self.nozzle.pk)]}, False), [200, 400])
        self.assertEqual(Shift.objects.for_tenant(self.tenant).count(), 1)

    def test_simultaneous_reversals_append_one_correction(self):
        assignment = self.start()
        sale = self.api_client().post("/api/v1/sales/", {"assignment_id": assignment, "closing_meter": "110.000"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(sale.status_code, 200, sale.data)
        Membership.objects.for_tenant(self.tenant).filter(pk=self.member.pk).update(permission_overrides={"shifts.manage": True})
        statuses = self.concurrent_posts("/api/v1/sales/"+sale.data["id"]+"/reverse/", {"reason": "Erroneous entry correction"}, False)
        self.assertEqual(statuses, [200, 400])
        self.assertEqual(InventoryMovement.objects.for_tenant(self.tenant).filter(kind="reversal").count(), 1)
        self.assertEqual(CashMovement.objects.for_tenant(self.tenant).filter(kind="reversal").count(), 1)

    def test_simultaneous_day_closures_reconcile_cash_once(self):
        Membership.objects.for_tenant(self.tenant).filter(pk=self.member.pk).update(permission_overrides={"inventory.manage": True, "closing.manage": True})
        physical = self.api_client().post("/api/v1/physical-stock/", {"tank_id": str(self.nozzle.tank_id), "measured_quantity": "500.000"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(physical.status_code, 200, physical.data)
        day = DailyClosing.objects.for_tenant(self.tenant).get()
        statuses = self.concurrent_posts("/api/v1/daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "5.00", "reason": "Documented counting correction"}, False)
        self.assertEqual(statuses, [200, 400])
        self.assertEqual(CashMovement.objects.for_tenant(self.tenant).filter(kind="reconciliation").count(), 1)

