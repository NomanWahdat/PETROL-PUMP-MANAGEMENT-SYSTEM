"""Explicit, repeat-safe sample data in the development demo station only."""
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw

from apps.audit.models import AuditLog
from apps.fuel.models import FuelProduct, FuelPriceHistory, Tank, Pump, Nozzle
from apps.customers.models import Customer
from apps.suppliers.models import Supplier
from apps.stations.models import Station
from apps.tenants.models import Tenant, Membership
from apps.operations import services as ops, serializers as inputs
from .create_demo_users import DEMO_SLUG


def demo_logo():
    """Simple original pump mark; owners can replace it with their own logo."""
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=48, fill="#edf5f1")
    draw.rounded_rectangle((70, 43, 162, 207), radius=12, fill="#39745e")
    draw.rounded_rectangle((84, 61, 148, 108), radius=6, fill="white")
    draw.line((63, 208, 174, 208), fill="#39745e", width=12)
    draw.line((162, 81, 191, 106, 191, 179), fill="#39745e", width=11)
    draw.arc((179, 165, 210, 195), 0, 180, fill="#39745e", width=10)
    draw.line((210, 180, 210, 90, 193, 72), fill="#39745e", width=10)
    draw.line((104, 154, 132, 154), fill="white", width=6)
    output = BytesIO()
    image.save(output, "PNG")
    return output.getvalue()


class Command(BaseCommand):
    help = "Add sample equipment, customers and transactions to Development Demo Station only. Requires DEBUG."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Sample data is disabled when DJANGO_DEBUG=false.")
        saved_logo = None
        try:
            with transaction.atomic():
                tenant = Tenant.objects.select_for_update().filter(slug=DEMO_SLUG, is_active=True).first()
                if tenant is None:
                    raise CommandError("Run create_demo_users first. Sample data can only use the development-demo station.")
                if AuditLog.objects.for_tenant(tenant).filter(action="demo_data_created").exists():
                    self.stdout.write("Demo data already exists. No records or transactions were added.")
                    return
                if FuelProduct.objects.for_tenant(tenant).exists():
                    raise CommandError("The demo station already has equipment. No existing records were changed.")
                members = {}
                for role in ["owner", "worker"]:
                    member = Membership.objects.for_tenant(tenant).select_related("user").filter(user__username="demo-"+role, user__is_active=True, role=role, is_active=True).first()
                    if member is None:
                        raise CommandError("The original active demo owner and worker memberships are required.")
                    members[role] = member
                def request_for(role):
                    member = members[role]
                    return SimpleNamespace(user=member.user, tenant=tenant, membership=member, session={"active_tenant_id": str(tenant.pk)}, headers={}, data={})
                owner, worker = request_for("owner"), request_for("worker")
                def create(model, **values):
                    return ops.create(model, owner, **values)
                def post(request, operation, permission, schema, payload, callback):
                    request.headers = {"Idempotency-Key": str(uuid4())}
                    request.data = payload
                    serializer = schema(data=payload)
                    serializer.is_valid(raise_exception=True)
                    return ops.execute(request, operation, permission, lambda: {"id": str(callback(serializer.validated_data).pk)})
                station = Station.objects.for_tenant(tenant).get()
                station.address = "Kabul — Development demonstration station"
                station.receipt_header = "Development demo — sample transaction"
                station.receipt_footer = "Thank you. This receipt is for demonstration only."
                station.save(update_fields=["address", "receipt_header", "receipt_footer", "updated_at"])
                equipment = []
                for index, (name, price, cost, opening, meter) in enumerate([
                    ("Petrol", "74.0000", "62.0000", "6500.000", "1000.000"),
                    ("Diesel", "70.0000", "59.0000", "5000.000", "2000.000"),
                ], 1):
                    product = create(FuelProduct, name=name, code=name.lower(), selling_price=price, purchase_price=cost, minimum_stock="1500.000", notes="Development sample")
                    create(FuelPriceHistory, product=product, selling_price=price, purchase_price=cost, reason="Initial demonstration price")
                    tank = create(Tank, name=name+" Tank", product=product, capacity="12000.000", opening_quantity=opening, minimum_stock="1500.000")
                    pump = create(Pump, name="Pump "+str(index), number=str(index), location="Forecourt")
                    nozzle = create(Nozzle, number="1", product=product, tank=tank, pump=pump, opening_meter=meter)
                    equipment.append((tank, nozzle))
                supplier = create(Supplier, name="Demo Fuel Supply", code="demo-supply", notes="Fictional demonstration supplier")
                create(Supplier, name="Demo Petroleum Trading", code="demo-trading", notes="Fictional demonstration supplier")
                customer = create(Customer, name="Demo Transport Company", code="demo-transport", credit_limit="20000.00", opening_balance="1500.00", notes="Fictional demonstration customer")
                create(Customer, name="Demo Construction Company", code="demo-construction", credit_limit="15000.00", opening_balance="0.00", notes="Fictional demonstration customer")
                post(owner, "demo.cash", "cash.manage", inputs.CashInput, {"kind": "deposit", "amount": "10000.00", "reason": "Development sample opening cash"}, lambda data: ops.post_cash(owner, data))
                post(owner, "demo.purchase", "purchases.manage", inputs.PurchaseInput, {"tank_id": str(equipment[1][0].pk), "supplier_id": str(supplier.pk), "quantity": "1500.000", "unit_cost": "59.0000", "paid_amount": "30000.00", "method": "bank", "invoice_number": "DEMO-001", "notes": "Development sample delivery"}, lambda data: ops.post_purchase(owner, data))
                closed = post(owner, "demo.shift.start", "shifts.own", inputs.StartShiftInput, {"nozzle_ids": [str(equipment[0][1].pk)], "opening_cash": "500.00", "notes": "Development sample completed shift"}, lambda data: ops.start_shift(owner, data))
                from apps.shifts.models import Shift
                shift = Shift.objects.for_tenant(tenant).get(pk=closed["id"])
                assignment = shift.assignments.get()
                post(owner, "demo.sale", "shifts.own", inputs.SaleInput, {"assignment_id": str(assignment.pk), "closing_meter": "1050.000", "customer_id": str(customer.pk), "cash_amount": "2000.00", "bank_amount": "1000.00", "credit_amount": "700.00", "notes": "Development sample split payment"}, lambda data: ops.post_sale(owner, data))
                post(owner, "demo.payment", "customers.manage", inputs.PaymentInput, {"customer_id": str(customer.pk), "shift_id": str(shift.pk), "amount": "100.00", "method": "cash", "notes": "Development sample customer collection"}, lambda data: ops.post_payment(owner, data))
                post(owner, "demo.shift.close", "shifts.own", inputs.CloseShiftInput, {"closing_meters": {str(assignment.pk): "1050.000"}, "counted_cash": "2600.00"}, lambda data: ops.close_shift(owner, shift, data))
                active = post(worker, "demo.shift.start", "shifts.own", inputs.StartShiftInput, {"nozzle_ids": [str(equipment[1][1].pk)], "opening_cash": "300.00", "notes": "Development sample active worker shift"}, lambda data: ops.start_shift(worker, data))
                worker_shift = Shift.objects.for_tenant(tenant).get(pk=active["id"])
                worker_assignment = worker_shift.assignments.get()
                post(worker, "demo.sale", "shifts.own", inputs.SaleInput, {"assignment_id": str(worker_assignment.pk), "closing_meter": "2035.000", "notes": "Development sample cash sale"}, lambda data: ops.post_sale(worker, data))
                if not tenant.logo_path:
                    saved_logo = default_storage.save(f"logos/{tenant.pk}/{uuid4()}.png", ContentFile(demo_logo()))
                    tenant.logo_path = saved_logo
                    tenant.save(update_fields=["logo_path", "updated_at"])
                ops.event(owner, "demo_data_created", tenant, {"products": 2, "tanks": 2, "pumps": 2, "nozzles": 2, "suppliers": 2, "customers": 2, "sales": 2, "shifts": 2, "purchases": 1, "payments": 1})
        except Exception:
            if saved_logo:
                default_storage.delete(saved_logo)
            raise
        self.stdout.write(self.style.SUCCESS("Sample data and a station logo added to Development Demo Station only. Worker has one active shift. Existing stations and passwords were preserved."))
