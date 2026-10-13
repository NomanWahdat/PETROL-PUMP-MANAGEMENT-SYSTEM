from decimal import Decimal
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction, connection
from django.test.utils import CaptureQueriesContext
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant, Membership, RolePolicy
from apps.stations.models import Station
from apps.employees.models import Employee
from apps.fuel.models import FuelProduct, Tank, Pump, Nozzle
from apps.shifts.models import Shift, NozzleAssignment
from apps.sales.models import FuelSale, MeterReading
from apps.suppliers.models import Supplier
from apps.customers.models import Customer, CustomerPayment
from apps.purchases.models import FuelPurchase
from apps.inventory.models import InventoryMovement, PhysicalStockReading
from apps.cash.models import CashMovement, DailyClosing
from apps.operations.models import OperationRequest
from apps.operations import services as ops

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FuelOperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = Tenant.objects.create(name="A", slug="ops-a")
        cls.b = Tenant.objects.create(name="B", slug="ops-b")
        cls.station = Station.all_tenants.create(tenant=cls.a, name="A")
        Station.all_tenants.create(tenant=cls.b, name="B")
        cls.users, cls.members = {}, {}
        for role in ["owner", "manager", "worker", "accountant"]:
            user = User.objects.create_user(username="ops-"+role, password="test-safe-password-392!")
            member = Membership.all_tenants.create(tenant=cls.a, user=user, role=role)
            Employee.all_tenants.create(tenant=cls.a, membership=member, name=role)
            cls.users[role], cls.members[role] = user, member
        cls.foreign_user = User.objects.create_user(username="ops-foreign")
        cls.foreign_member = Membership.all_tenants.create(tenant=cls.b, user=cls.foreign_user, role="worker")
        cls.products, cls.tanks, cls.nozzles, cls.suppliers, cls.customers = {}, {}, {}, {}, {}
        for tenant in [cls.a, cls.b]:
            product = FuelProduct.all_tenants.create(tenant=tenant, name="Diesel", code="diesel", selling_price=Decimal("73.4567"))
            tank = Tank.all_tenants.create(tenant=tenant, name="Tank", product=product, capacity=1000, opening_quantity=500)
            pump = Pump.all_tenants.create(tenant=tenant, name="Pump", number="1")
            nozzle = Nozzle.all_tenants.create(tenant=tenant, number="1", pump=pump, tank=tank, product=product, opening_meter=100)
            supplier = Supplier.all_tenants.create(tenant=tenant, name="Supplier", code="supplier")
            customer = Customer.all_tenants.create(tenant=tenant, name="Customer", code="customer", credit_limit=10000)
            for collection, record in [(cls.products, product), (cls.tanks, tank), (cls.nozzles, nozzle), (cls.suppliers, supplier), (cls.customers, customer)]:
                collection[tenant.pk] = record

    def client_for(self, role="owner", enforce_csrf=False):
        client = APIClient(enforce_csrf_checks=enforce_csrf)
        client.force_login(self.users[role])
        session = client.session
        session["active_tenant_id"] = str(self.a.pk)
        session.save()
        return client

    def post(self, path, body, role="owner", key=None):
        return self.client_for(role).post("/api/v1/"+path, body, format="json", HTTP_IDEMPOTENCY_KEY=str(key or uuid4()))

    def start(self, role="worker"):
        response = self.post("shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)], "opening_cash": "0.00"}, role)
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def sale(self, shift, closing="110.000", **extra):
        response = self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": closing, **extra}, "worker")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def close(self, shift, counted="0.00", meter="100.000", role="worker", **extra):
        return self.post("shifts/"+shift["id"]+"/close/", {"closing_meters": {shift["assignments"][0]["id"]: meter}, "counted_cash": counted, **extra}, role)

    def test_complete_meter_sale_stock_cash_receipt_flow(self):
        shift = self.start()
        sale = self.sale(shift)
        self.assertEqual(sale["liters"], "10.000")
        self.assertEqual(sale["total"], "734.57")
        self.assertEqual(sale["cash_amount"], "734.57")
        self.assertEqual(ops.stock(self.a, self.tanks[self.a.pk]), Decimal("490.000"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("734.57"))
        receipt = self.client_for("worker").get("/api/v1/sales/"+sale["id"]+"/receipt/")
        self.assertEqual(receipt.data["receipt_snapshot"]["station_name"], "A")
        self.assertEqual(self.close(shift, "734.57", "110.000").status_code, 200)
        self.assertEqual(NozzleAssignment.objects.for_tenant(self.a).get().is_active, False)

    def test_duplicate_sale_is_replayed_without_duplicate_movements(self):
        shift = self.start()
        payload = {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "110.000"}
        key = uuid4()
        first = self.post("sales/", payload, "worker", key)
        second = self.post("sales/", payload, "worker", key)
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data, second.data)
        self.assertEqual(FuelSale.objects.for_tenant(self.a).count(), 1)
        self.assertEqual(InventoryMovement.objects.for_tenant(self.a).count(), 1)
        self.assertEqual(CashMovement.objects.for_tenant(self.a).count(), 1)
        payload["closing_meter"] = "111.000"
        self.assertEqual(self.post("sales/", payload, "worker", key).status_code, 409)
        self.assertEqual(self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "110.000"}, "owner", key).status_code, 409)

    def test_post_requires_idempotency_and_csrf(self):
        response = self.client_for("worker").post("/api/v1/shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client_for("worker", True).post("/api/v1/shifts/", {}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 403)

    def test_shift_cash_pickup_updates_drawer_and_station_book_once(self):
        self.post("cash-movements/", {"kind": "deposit", "amount": "100.00", "reason": "Initial station cash"})
        shift = self.post("shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)], "opening_cash": "100.00"}, "worker").data
        response = self.post("cash-movements/", {"kind": "withdrawal", "amount": "30.00", "shift_id": shift["id"], "reason": "Drawer pickup to external bank"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ops.shift_cash(self.a, Shift.objects.for_tenant(self.a).get()), Decimal("70.00"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("70.00"))
        self.assertEqual(self.close(shift, counted="70.00").status_code, 200)

    def test_foreign_operational_ledgers_payments_and_receipts_are_hidden(self):
        day = DailyClosing.all_tenants.create(tenant=self.b, business_date="2026-01-01")
        shift = Shift.all_tenants.create(tenant=self.b, day=day, attendant=self.foreign_member, reference="B")
        assignment = NozzleAssignment.all_tenants.create(tenant=self.b, shift=shift, nozzle=self.nozzles[self.b.pk], tank=self.tanks[self.b.pk], product=self.products[self.b.pk], opening_meter=100, unit_price=1)
        reading = MeterReading.all_tenants.create(tenant=self.b, day=day, assignment=assignment, opening_meter=100, closing_meter=110, liters=10)
        sale = FuelSale.all_tenants.create(tenant=self.b, day=day, shift=shift, reading=reading, customer=self.customers[self.b.pk], reference="B", unit_price=1, subtotal=10, total=10, cash_amount=0, credit_amount=10, currency="AFN")
        purchase = FuelPurchase.all_tenants.create(tenant=self.b, day=day, supplier=self.suppliers[self.b.pk], tank=self.tanks[self.b.pk], product=self.products[self.b.pk], quantity=1, unit_cost=1, total=1, reference="B")
        payment = CustomerPayment.all_tenants.create(tenant=self.b, day=day, customer=self.customers[self.b.pk], shift=shift, amount=5, reference="B")
        movement = InventoryMovement.all_tenants.create(tenant=self.b, day=day, tank=self.tanks[self.b.pk], purchase=purchase, kind="purchase", quantity=1)
        physical = PhysicalStockReading.all_tenants.create(tenant=self.b, day=day, tank=self.tanks[self.b.pk], expected_quantity=500, measured_quantity=500, variance=0)
        cash = CashMovement.all_tenants.create(tenant=self.b, day=day, shift=shift, kind="deposit", amount=10)
        for path, record in [("sales",sale), ("meter-readings",reading), ("purchases",purchase), ("customer-payments",payment), ("inventory-movements",movement), ("physical-stock",physical), ("cash-movements",cash)]:
            with self.subTest(path=path):
                client = self.client_for()
                self.assertEqual(client.get("/api/v1/"+path+"/"+str(record.pk)+"/").status_code, 404)
                self.assertNotIn(str(record.pk), str(client.get("/api/v1/"+path+"/?tenant_id="+str(self.b.pk)).data))
        self.assertEqual(self.client_for().get("/api/v1/sales/"+str(sale.pk)+"/receipt/").status_code, 404)
        self.assertEqual(self.client_for().get("/api/v1/customer-payments/"+str(payment.pk)+"/receipt/").status_code, 404)

    def test_float_inputs_rejected_and_client_totals_ignored(self):
        shift = self.start()
        self.assertEqual(self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": 110.1}, "worker").status_code, 400)
        sale = self.sale(shift, total="1.00", liters="99", tenant_id=str(self.b.pk))
        self.assertEqual(sale["total"], "734.57")
        self.assertEqual(FuelSale.objects.for_tenant(self.a).get().tenant_id, self.a.pk)

    def test_meter_continuity_and_negative_zero_rejected(self):
        shift = self.start()
        for closing in ["99.000", "100.000"]:
            self.assertEqual(self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": closing}, "worker").status_code, 400)
        self.sale(shift)
        second = self.sale(shift, "113.333")
        self.assertEqual(second["opening_meter"], "110.000")
        self.assertEqual(second["liters"], "3.333")
        self.assertEqual(second["total"], "244.83")

    def test_stock_shortage_rolls_back_all_records(self):
        shift = self.start()
        response = self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "601.000"}, "worker")
        self.assertEqual(response.status_code, 400)
        for model in [FuelSale, MeterReading, InventoryMovement, CashMovement]:
            self.assertEqual(model.objects.for_tenant(self.a).count(), 0)

    def test_price_and_tax_snapshots_survive_configuration_changes(self):
        self.station.settings = {"tax_enabled": True, "tax_rate": "10.0000"}
        self.station.save()
        shift = self.start()
        self.products[self.a.pk].selling_price = Decimal("99.0000")
        self.products[self.a.pk].save()
        sale = self.sale(shift)
        self.assertEqual(sale["unit_price"], "73.4567")
        self.assertEqual(sale["tax_amount"], "73.46")
        self.assertEqual(sale["total"], "808.03")

    def test_nozzle_and_attendant_double_assignment_rejected(self):
        shift = self.start()
        response = self.post("shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)]}, "manager")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.post("shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)]}, "worker").status_code, 400)
        self.assertEqual(Shift.objects.for_tenant(self.a).count(), 1)

    def test_workers_cannot_start_for_others_or_manage_transactions(self):
        self.assertEqual(self.post("shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)], "attendant_id": str(self.members["owner"].pk)}, "worker").status_code, 403)
        for path in ["suppliers/", "purchases/", "cash-movements/", "physical-stock/"]:
            self.assertEqual(self.post(path, {}, "worker").status_code, 403)
        self.assertEqual(self.client_for("worker").get("/api/v1/inventory-movements/").status_code, 403)

    def test_worker_only_sees_own_shift_sales_and_receipts(self):
        shift = self.start("owner")
        sale = self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "110.000"}).data
        client = self.client_for("worker")
        for path, identifier in [("shifts", shift["id"]), ("sales", sale["id"])]:
            self.assertEqual(client.get("/api/v1/"+path+"/").data["count"], 0)
            self.assertEqual(client.get("/api/v1/"+path+"/"+identifier+"/").status_code, 404)
        self.assertEqual(client.get("/api/v1/sales/"+sale["id"]+"/receipt/").status_code, 404)

    def test_accountant_cannot_start_or_post_fuel_sales(self):
        for path in ["shifts/", "sales/", "purchases/"]:
            self.assertEqual(self.post(path, {}, "accountant").status_code, 403)
        self.assertEqual(self.client_for("accountant").get("/api/v1/sales/").status_code, 200)

    def test_credit_sale_split_payment_limit_and_customer_payment(self):
        shift = self.start()
        sale = self.sale(shift, customer_id=str(self.customers[self.a.pk].pk), credit_amount="300.00", bank_amount="100.00")
        self.assertEqual(sale["cash_amount"], "334.57")
        self.assertEqual(ops.customer_balance(self.a, self.customers[self.a.pk]), Decimal("300.00"))
        payment = self.post("customer-payments/", {"customer_id": str(self.customers[self.a.pk].pk), "amount": "100.00"}, "worker")
        self.assertEqual(payment.status_code, 200, payment.data)
        self.assertEqual(ops.customer_balance(self.a, self.customers[self.a.pk]), Decimal("200.00"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("434.57"))
        self.assertEqual(self.post("customer-payments/", {"customer_id": str(self.customers[self.a.pk].pk), "amount": "201.00"}, "worker").status_code, 400)

    def test_credit_limit_and_missing_customer_reject_sale(self):
        shift = self.start()
        customer = self.customers[self.a.pk]
        customer.credit_limit = Decimal("5.00")
        customer.save()
        for payload in [{"credit_amount": "6.00", "customer_id": str(customer.pk)}, {"credit_amount": "1.00"}]:
            self.assertEqual(self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "110.000", **payload}, "worker").status_code, 400)
        self.assertEqual(FuelSale.objects.for_tenant(self.a).count(), 0)

    def test_customer_private_balance_not_exposed_to_worker(self):
        customer = self.customers[self.a.pk]
        response = self.client_for("worker").get("/api/v1/customers/"+str(customer.pk)+"/")
        self.assertEqual(set(response.data), {"id", "name", "phone", "is_active"})
        self.assertIn("balance", self.client_for().get("/api/v1/customers/"+str(customer.pk)+"/").data)

    def test_close_shift_requires_all_final_meters_and_correct_cash(self):
        shift = self.start()
        self.sale(shift)
        self.assertEqual(self.close(shift, "734.57", "111.000").status_code, 400)
        self.assertEqual(self.close(shift, "700.00", "110.000").status_code, 400)
        self.assertEqual(self.close(shift, "700.00", "110.000", role="manager", reason="Drawer shortage approved").status_code, 200)
        self.assertEqual(self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "112.000"}, "worker").status_code, 400)

    def test_latest_sale_reversal_preserves_meter_inventory_cash_history(self):
        shift = self.start()
        sale = self.sale(shift)
        self.assertEqual(self.post("sales/"+sale["id"]+"/reverse/", {"reason": "Wrong final meter entered"}, "worker").status_code, 403)
        result = self.post("sales/"+sale["id"]+"/reverse/", {"reason": "Wrong final meter entered"})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(MeterReading.objects.for_tenant(self.a).count(), 2)
        self.assertEqual(ops.current_meter(self.a, self.nozzles[self.a.pk]), Decimal("100.000"))
        self.assertEqual(ops.stock(self.a, self.tanks[self.a.pk]), Decimal("500.000"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("0.00"))
        self.assertEqual(self.sale(shift)["liters"], "10.000")
        self.assertEqual(self.post("sales/"+sale["id"]+"/reverse/", {"reason": "Duplicate reversal"}).status_code, 400)

    def test_non_latest_meter_sale_cannot_be_reversed(self):
        shift = self.start()
        sale = self.sale(shift)
        self.sale(shift, "111.000")
        self.assertEqual(self.post("sales/"+sale["id"]+"/reverse/", {"reason": "Wrong reading"}).status_code, 400)

    def test_purchases_add_stock_and_cash_payment_reversal(self):
        deposit = self.post("cash-movements/", {"kind": "deposit", "amount": "10000.00", "reason": "Initial cash fund"})
        self.assertEqual(deposit.status_code, 200, deposit.data)
        response = self.post("purchases/", {"tank_id": str(self.tanks[self.a.pk].pk), "supplier_id": str(self.suppliers[self.a.pk].pk), "quantity": "100.000", "unit_cost": "60.1234", "paid_amount": "5000.00"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["total"], "6012.34")
        self.assertEqual(ops.stock(self.a, self.tanks[self.a.pk]), Decimal("600.000"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("5000.00"))
        result = self.post("purchases/"+response.data["id"]+"/reverse/", {"reason": "Delivery entered twice"})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(ops.stock(self.a, self.tanks[self.a.pk]), Decimal("500.000"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("10000.00"))

    def test_purchase_capacity_and_insufficient_cash_rejected(self):
        payload = {"tank_id": str(self.tanks[self.a.pk].pk), "supplier_id": str(self.suppliers[self.a.pk].pk), "quantity": "501.000", "unit_cost": "1.0000"}
        self.assertEqual(self.post("purchases/", payload).status_code, 400)
        payload.update(quantity="1.000", paid_amount="1.00")
        self.assertEqual(self.post("purchases/", payload).status_code, 400)
        self.assertEqual(FuelPurchase.objects.for_tenant(self.a).count(), 0)

    def test_cash_withdrawal_cannot_exceed_balance(self):
        self.assertEqual(self.post("cash-movements/", {"kind": "withdrawal", "amount": "1.00", "reason": "Petty cash"}).status_code, 400)
        self.post("cash-movements/", {"kind": "deposit", "amount": "100.00", "reason": "Opening fund"})
        self.assertEqual(self.post("cash-movements/", {"kind": "withdrawal", "amount": "30.00", "reason": "Safe transfer"}).status_code, 200)
        self.assertEqual(ops.cash_balance(self.a), Decimal("70.00"))

    def test_physical_reading_variance_is_not_implicit_adjustment(self):
        reading = self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "498.500"})
        self.assertEqual(reading.status_code, 200, reading.data)
        self.assertEqual(reading.data["variance"], "-1.500")
        self.assertEqual(ops.stock(self.a, self.tanks[self.a.pk]), Decimal("500.000"))
        adjusted = self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "498.500", "apply_adjustment": True, "reason": "Approved dip measurement correction"})
        self.assertEqual(adjusted.status_code, 200, adjusted.data)
        self.assertEqual(ops.stock(self.a, self.tanks[self.a.pk]), Decimal("498.500"))

    def test_physical_stock_blocked_during_open_shift(self):
        self.start()
        self.assertEqual(self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "500.000"}).status_code, 400)

    def test_daily_closing_requires_closed_shifts_and_fresh_physical_stock(self):
        shift = self.start()
        sale = self.sale(shift)
        day = DailyClosing.objects.for_tenant(self.a).get()
        self.assertEqual(self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "734.57"}).status_code, 400)
        self.assertEqual(self.close(shift, "734.57", "110.000").status_code, 200)
        self.assertEqual(self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "734.57"}).status_code, 400)
        self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "490.000"})
        result = self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "734.57"})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["snapshot"]["sales_total"], "734.57")
        self.assertEqual(Decimal(result.data["snapshot"]["liters_sold"]), Decimal("10.000"))
        self.assertEqual(self.post("shifts/", {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)]}, "worker").status_code, 400)
        self.assertEqual(self.post("sales/"+sale["id"]+"/reverse/", {"reason": "Wrong entry"}).status_code, 400)

    def test_day_cash_difference_is_audited_and_reconciles_ledger(self):
        self.post("cash-movements/", {"kind": "deposit", "amount": "100.00", "reason": "Initial cash"})
        self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "500.000"})
        day = DailyClosing.objects.for_tenant(self.a).get()
        self.assertEqual(self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "90.00"}).status_code, 400)
        response = self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "90.00", "reason": "Documented cash shortage"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["cash_difference"], "-10.00")
        self.assertEqual(ops.cash_balance(self.a), Decimal("90.00"))

    def test_reopening_restores_only_latest_safe_assignments(self):
        shift = self.start()
        self.assertEqual(self.close(shift).status_code, 200)
        response = self.post("shifts/"+shift["id"]+"/reopen/", {"reason": "Recheck handover"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(NozzleAssignment.objects.for_tenant(self.a).get().is_active)
        self.assertEqual(self.close(shift).status_code, 200)
        self.start("owner")
        self.assertEqual(self.post("shifts/"+shift["id"]+"/reopen/", {"reason": "Late correction"}).status_code, 400)

    def test_paused_equipment_and_revoked_attendants_cannot_resume_operations(self):
        shift = self.start()
        pump = self.nozzles[self.a.pk].pump
        response = self.client_for().patch("/api/v1/pumps/"+str(pump.pk)+"/", {"status": "maintenance"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "110.000"}, "worker")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(FuelSale.objects.for_tenant(self.a).exists())
        self.assertEqual(self.close(shift).status_code, 200)
        url = "shifts/"+shift["id"]+"/reopen/"
        self.assertEqual(self.post(url, {"reason": "Recheck handover"}).status_code, 400)
        Pump.objects.for_tenant(self.a).filter(pk=pump.pk).update(status="ready")
        Membership.objects.for_tenant(self.a).filter(pk=self.members["worker"].pk).update(is_active=False)
        self.assertEqual(self.post(url, {"reason": "Recheck handover"}).status_code, 400)
        self.assertEqual(Shift.objects.for_tenant(self.a).get().status, "closed")
        self.assertFalse(NozzleAssignment.objects.for_tenant(self.a).get().is_active)

    def test_closed_day_can_be_reopened_with_reason(self):
        self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "500.000"})
        day = DailyClosing.objects.for_tenant(self.a).get()
        self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "0.00"})
        self.assertEqual(self.post("daily-closings/"+str(day.pk)+"/reopen/", {}).status_code, 400)
        response = self.post("daily-closings/"+str(day.pk)+"/reopen/", {"reason": "Authorized reconciliation"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "open")

    def test_all_lists_details_and_relations_are_tenant_isolated(self):
        other_day = DailyClosing.all_tenants.create(tenant=self.b, business_date="2026-01-01")
        other_shift = Shift.all_tenants.create(tenant=self.b, day=other_day, attendant=self.foreign_member, reference="B")
        other_assignment = NozzleAssignment.all_tenants.create(tenant=self.b, shift=other_shift, nozzle=self.nozzles[self.b.pk], tank=self.tanks[self.b.pk], product=self.products[self.b.pk], opening_meter=100, unit_price=1)
        for path, record in [("suppliers", self.suppliers[self.b.pk]), ("customers", self.customers[self.b.pk]), ("daily-closings", other_day), ("shifts", other_shift)]:
            self.assertEqual(self.client_for().get("/api/v1/"+path+"/"+str(record.pk)+"/").status_code, 404)
            result = self.client_for().get("/api/v1/"+path+"/?tenant_id="+str(self.b.pk), HTTP_X_TENANT_ID=str(self.b.pk))
            self.assertNotIn(str(record.pk), str(result.data))
        for payload in [
            {"nozzle_ids": [str(self.nozzles[self.b.pk].pk)]},
            {"nozzle_ids": [str(self.nozzles[self.a.pk].pk)], "attendant_id": str(self.foreign_member.pk)},
        ]:
            self.assertEqual(self.post("shifts/", payload).status_code, 404)
        self.assertEqual(self.post("sales/", {"assignment_id": str(other_assignment.pk), "closing_meter": "110.000"}).status_code, 404)
        self.assertEqual(self.post("purchases/", {"tank_id": str(self.tanks[self.b.pk].pk), "supplier_id": str(self.suppliers[self.a.pk].pk), "quantity": "1.000", "unit_cost": "1.0000"}).status_code, 404)
        self.assertEqual(self.post("customer-payments/", {"customer_id": str(self.customers[self.b.pk].pk), "amount": "1.00"}).status_code, 404)

    def test_direct_database_cross_tenant_operational_relations_rejected(self):
        day = DailyClosing.all_tenants.create(tenant=self.a, business_date="2026-01-01")
        with self.assertRaises(IntegrityError), transaction.atomic():
            shift = Shift.all_tenants.create(tenant=self.a, day=day, attendant=self.foreign_member, reference="bad")
            transaction.get_connection().check_constraints()
        with self.assertRaises(IntegrityError), transaction.atomic():
            InventoryMovement.all_tenants.create(tenant=self.a, day=day, tank=self.tanks[self.b.pk], kind="purchase", quantity=1)
            transaction.get_connection().check_constraints()

    def test_transaction_deletion_and_arbitrary_editing_unavailable(self):
        shift = self.start()
        sale = self.sale(shift)
        for path, record_id in [("sales", sale["id"]), ("shifts", shift["id"]), ("meter-readings", str(MeterReading.objects.for_tenant(self.a).get().pk))]:
            self.assertEqual(self.client_for().delete("/api/v1/"+path+"/"+record_id+"/").status_code, 405)
            self.assertEqual(self.client_for().patch("/api/v1/"+path+"/"+record_id+"/", {"total": "1.00"}, format="json").status_code, 405)

    def test_setup_fields_locked_after_operational_use(self):
        self.start()
        tank = self.tanks[self.a.pk]
        nozzle = self.nozzles[self.a.pk]
        self.assertEqual(self.client_for().patch("/api/v1/tanks/"+str(tank.pk)+"/", {"opening_quantity": "600.000"}, format="json").status_code, 400)
        self.assertEqual(self.client_for().patch("/api/v1/nozzles/"+str(nozzle.pk)+"/", {"tank": None}, format="json").status_code, 400)
        self.assertEqual(self.client_for().patch("/api/v1/station/", {"currency": "USD"}, format="json").status_code, 400)

    def test_bank_payments_do_not_increase_drawer_cash_and_have_receipts(self):
        shift = self.start()
        self.sale(shift, customer_id=str(self.customers[self.a.pk].pk), credit_amount="734.57")
        payment = self.post("customer-payments/", {"customer_id": str(self.customers[self.a.pk].pk), "amount": "100.00", "method": "bank"}, "worker")
        self.assertEqual(payment.status_code, 200, payment.data)
        receipt = self.client_for("worker").get("/api/v1/customer-payments/"+payment.data["id"]+"/receipt/")
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.data["receipt_snapshot"]["customer_name"], "Customer")
        self.assertEqual(ops.cash_balance(self.a), Decimal("0.00"))

    def test_customer_payment_reversal_restores_debt_and_cash(self):
        shift = self.start()
        self.sale(shift, customer_id=str(self.customers[self.a.pk].pk), credit_amount="300.00")
        payment = self.post("customer-payments/", {"customer_id": str(self.customers[self.a.pk].pk), "amount": "100.00"}, "worker").data
        result = self.post("customer-payments/"+payment["id"]+"/reverse/", {"reason": "Incorrect customer payment"})
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(ops.customer_balance(self.a, self.customers[self.a.pk]), Decimal("300.00"))
        self.assertEqual(ops.cash_balance(self.a), Decimal("434.57"))

    def test_credit_sale_with_collected_payment_must_reverse_payment_first(self):
        shift = self.start()
        sale = self.sale(shift, customer_id=str(self.customers[self.a.pk].pk), credit_amount="300.00")
        self.post("customer-payments/", {"customer_id": str(self.customers[self.a.pk].pk), "amount": "100.00"}, "worker")
        self.assertEqual(self.post("sales/"+sale["id"]+"/reverse/", {"reason": "Wrong meter"}).status_code, 400)

    def test_duplicate_delivery_invoice_is_rejected_even_with_new_key(self):
        payload = {"tank_id": str(self.tanks[self.a.pk].pk), "supplier_id": str(self.suppliers[self.a.pk].pk), "quantity": "1.000", "unit_cost": "1.0000", "invoice_number": "INV-100"}
        self.assertEqual(self.post("purchases/", payload).status_code, 200)
        self.assertEqual(self.post("purchases/", payload).status_code, 400)
        self.assertEqual(FuelPurchase.objects.for_tenant(self.a).count(), 1)

    def test_day_closing_rejects_stale_physical_reading_after_delivery(self):
        self.post("physical-stock/", {"tank_id": str(self.tanks[self.a.pk].pk), "measured_quantity": "500.000"})
        self.post("purchases/", {"tank_id": str(self.tanks[self.a.pk].pk), "supplier_id": str(self.suppliers[self.a.pk].pk), "quantity": "1.000", "unit_cost": "1.0000"})
        day = DailyClosing.objects.for_tenant(self.a).get()
        self.assertEqual(self.post("daily-closings/"+str(day.pk)+"/close/", {"counted_cash": "0.00"}).status_code, 400)

    def test_large_calculated_amount_returns_validation_not_server_error(self):
        product = self.products[self.a.pk]
        product.selling_price = Decimal("99999999999999.0000")
        product.save()
        shift = self.start()
        response = self.post("sales/", {"assignment_id": shift["assignments"][0]["id"], "closing_meter": "600.000"}, "worker")
        self.assertEqual(response.status_code, 400)

    def test_custom_purchase_permission_can_use_its_own_domain_only(self):
        RolePolicy.all_tenants.create(tenant=self.a, role="worker", permissions=["station.view", "purchases.manage"])
        client = self.client_for("worker")
        for path in ["suppliers/", "purchases/"]:
            self.assertEqual(client.get("/api/v1/"+path).status_code, 200)
        options = client.get("/api/v1/operations/options/")
        self.assertEqual(options.status_code, 200)
        self.assertIn("tanks", options.data)
        self.assertIn("suppliers", options.data)
        self.assertNotIn("cash_balance", options.data)
        self.assertEqual(options.data["customers"], [])
        self.assertEqual(client.get("/api/v1/sales/").status_code, 403)
        self.assertEqual(self.post("purchases/", {"tank_id": str(self.tanks[self.a.pk].pk), "supplier_id": str(self.suppliers[self.a.pk].pk), "quantity": "1.000", "unit_cost": "1.0000"}, "worker").status_code, 200)

    def test_custom_customer_manager_can_read_station_payments_and_receipts(self):
        customer = self.customers[self.a.pk]
        Customer.objects.for_tenant(self.a).filter(pk=customer.pk).update(opening_balance=100)
        payment = self.post("customer-payments/", {"customer_id": str(customer.pk), "amount": "20.00", "method": "bank"}).data
        RolePolicy.all_tenants.create(tenant=self.a, role="worker", permissions=["station.view", "customers.manage"])
        client = self.client_for("worker")
        listing = client.get("/api/v1/customer-payments/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(client.get("/api/v1/customer-payments/"+payment["id"]+"/receipt/").status_code, 200)
        self.assertEqual(client.get("/api/v1/sales/").status_code, 403)

    def test_closing_meter_float_is_rejected_without_changing_shift(self):
        shift = self.start()
        response = self.close(shift, meter=100.0)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Shift.objects.for_tenant(self.a).get().status, "open")

    def test_operational_filters_validate_status_and_day_and_limit_page_size(self):
        self.start()
        client = self.client_for()
        response = client.get("/api/v1/daily-closings/?status=closed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        for path in ["shifts/?status=unknown", "sales/?day=bad", "daily-closings/?status=unknown"]:
            self.assertEqual(client.get("/api/v1/"+path).status_code, 400)
        self.assertEqual(client.get("/api/v1/shifts/?page_size=999999").status_code, 200)

    def test_customer_balances_remain_exact_without_per_row_queries(self):
        shift = self.start()
        self.sale(shift, closing="101.000", credit_amount="20.00", customer_id=str(self.customers[self.a.pk].pk))
        self.post("customer-payments/", {"customer_id": str(self.customers[self.a.pk].pk), "amount": "10.00", "method": "bank"})
        client = self.client_for()
        with CaptureQueriesContext(connection) as baseline:
            response = client.get("/api/v1/customers/?page_size=200")
        self.assertEqual(response.data["results"][0]["balance"], "10.00")
        Customer.all_tenants.bulk_create([Customer(tenant=self.a, code=f"extra-{index}", name=f"Extra {index}", opening_balance=20, credit_limit=1000) for index in range(25)])
        with CaptureQueriesContext(connection) as larger:
            response = client.get("/api/v1/customers/?page_size=200")
        self.assertEqual(response.data["count"], 26)
        self.assertLessEqual(len(larger), len(baseline)+1)
        self.assertTrue(all(row["balance"] == "20.00" for row in response.data["results"] if row["code"].startswith("extra-")))

    def test_shift_history_query_count_does_not_grow_with_assignments(self):
        shift = self.start()
        client = self.client_for()
        with CaptureQueriesContext(connection) as baseline:
            response = client.get("/api/v1/shifts/?page_size=200")
        self.assertEqual(response.status_code, 200)
        day = DailyClosing.objects.for_tenant(self.a).get()
        nozzle = self.nozzles[self.a.pk]
        for index in range(12):
            old = Shift.all_tenants.create(tenant=self.a, day=day, attendant=self.members["worker"], reference=f"OLD-{index}", status="closed", opening_cash=5)
            NozzleAssignment.all_tenants.create(tenant=self.a, shift=old, nozzle=nozzle, tank=nozzle.tank, product=nozzle.product, opening_meter=100, unit_price=70, is_active=False)
            CashMovement.all_tenants.create(tenant=self.a, day=day, shift=old, kind="deposit", amount=1)
        with CaptureQueriesContext(connection) as larger:
            response = client.get("/api/v1/shifts/?page_size=200")
        self.assertEqual(response.data["count"], 13)
        self.assertLessEqual(len(larger), len(baseline)+1)
        self.assertTrue(all(row["current_expected_cash"] == "6.00" for row in response.data["results"] if row["reference"].startswith("OLD-")))

