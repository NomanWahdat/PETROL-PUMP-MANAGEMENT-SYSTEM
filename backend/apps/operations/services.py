"""Atomic, tenant-scoped operational posting. All arithmetic is Decimal."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP, localcontext
from zoneinfo import ZoneInfo

from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.common.api import validated_save
from apps.common.errors import CodedError
from apps.tenants.models import Tenant, Membership
from apps.tenants.permissions import effective_permissions, lock_tenant_access
from apps.stations.models import Station
from apps.fuel.models import Nozzle, Tank
from apps.shifts.models import Shift, NozzleAssignment
from apps.sales.models import MeterReading, FuelSale
from apps.purchases.models import FuelPurchase
from apps.suppliers.models import Supplier
from apps.customers.models import Customer, CustomerPayment
from apps.inventory.models import InventoryMovement, PhysicalStockReading
from apps.cash.models import CashMovement, DailyClosing
from .models import OperationRequest

ZERO = Decimal("0")
CENT = Decimal("0.01")
VOLUME = Decimal("0.001")


def money(value):
    with localcontext() as context:
        context.prec = 50
        result = value.quantize(CENT, rounding=ROUND_HALF_UP)
    if abs(result) >= Decimal('10000000000000000'):
        raise serializers.ValidationError({"amount": "Calculated amount exceeds the supported range."})
    return result


def safe_json(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def fail(code, message, status=400):
    raise CodedError(code, message, status)


def scoped(model, tenant):
    return model.objects.for_tenant(tenant)


def find(model, tenant, pk):
    return get_object_or_404(scoped(model, tenant), pk=pk)


def total(query, field):
    value = query.aggregate(value=Sum(field))["value"] or ZERO
    return value.quantize(VOLUME if field.endswith(("quantity", "liters")) else CENT, rounding=ROUND_HALF_UP)


def stock(tenant, tank):
    return tank.opening_quantity + total(scoped(InventoryMovement, tenant).filter(tank=tank), "quantity")


def cash_balance(tenant):
    return total(scoped(CashMovement, tenant), "amount")


def customer_balance(tenant, customer):
    return customer.opening_balance + total(scoped(FuelSale, tenant).filter(customer=customer, status="posted"), "credit_amount") - total(scoped(CustomerPayment, tenant).filter(customer=customer, status="posted"), "amount")


def current_meter(tenant, nozzle):
    reading = scoped(MeterReading, tenant).filter(assignment__nozzle=nozzle).order_by("-created_at", "-id").first()
    return reading.closing_meter if reading else nozzle.opening_meter


def reference(model, tenant, prefix):
    return f"{prefix}-{scoped(model, tenant).count()+1:06d}"


def create(model, request, **values):
    instance = model(tenant=request.tenant, created_by=request.user, **values)
    validated_save(instance)
    return instance


def event(request, action, instance, changes=None):
    AuditLog.all_tenants.create(tenant=request.tenant, created_by=request.user, action=action, object_type=instance._meta.label_lower, object_id=str(instance.pk), changes=safe_json(changes or {}))


def execute(request, operation, permission, callback):
    """Serializes a station's posts, rechecks authorization, stores one replayable response."""
    key = serializers.UUIDField().run_validation(request.headers.get("Idempotency-Key"))
    fingerprint = hashlib.sha256(json.dumps(request.data, sort_keys=True, default=str).encode()).hexdigest()
    try:
        with transaction.atomic():
            tenant = lock_tenant_access(request, permission)
            previous = scoped(OperationRequest, tenant).filter(key=key).first()
            if previous:
                if previous.created_by_id != request.user.pk or previous.operation != operation or previous.fingerprint != fingerprint:
                    fail("idempotency_conflict", "This submission key was already used for different information.", 409)
                return previous.response
            response = safe_json(callback())
            create(OperationRequest, request, key=key, operation=operation, fingerprint=fingerprint, response=response)
            return response
    except IntegrityError as exc:
        raise serializers.ValidationError({"record": "A conflicting operational record exists."}) from exc


def open_day(request):
    day = scoped(DailyClosing, request.tenant).filter(status="open").first()
    if day:
        return day
    station = scoped(Station, request.tenant).get()
    today = timezone.localtime(timezone.now(), ZoneInfo(station.timezone)).date()
    if scoped(DailyClosing, request.tenant).filter(business_date__gte=today).exists():
        fail("day_closed", "Today's station day is closed. Reopen it before posting.")
    return create(DailyClosing, request, business_date=today, opening_cash=cash_balance(request.tenant))


def require_open(day):
    if day.status != "open":
        fail("day_closed", "Closed days cannot be changed. Reopen the latest day first.")


def own_shift(request, shift):
    permissions = effective_permissions(request.membership)
    if "shifts.manage" not in permissions and shift.attendant_id != request.membership.pk:
        fail("permission_denied", "Only your assigned shift is available.", 403)


def active_shift(request, shift):
    own_shift(request, shift)
    require_open(shift.day)
    if shift.status != "open":
        fail("shift_closed", "Reopen this shift before changing its transactions.")


def shift_cash(tenant, shift):
    return shift.opening_cash + total(scoped(CashMovement, tenant).filter(shift=shift), "amount")


def movement(request, model, **values):
    field = "quantity" if model is InventoryMovement else "amount"
    if values[field] != ZERO:
        return create(model, request, **values)


def require_ready_nozzle(nozzle):
    if not nozzle.is_active or not nozzle.pump.is_active or nozzle.pump.status != "ready" or not nozzle.product.is_active or not nozzle.tank_id or not nozzle.tank.is_active:
        fail("equipment_unavailable", "Choose ready nozzles connected to active tanks.")


def start_shift(request, data):
    day = open_day(request)
    attendant = find(Membership, request.tenant, data.get("attendant_id") or request.membership.pk)
    if not attendant.is_active or not attendant.user.is_active:
        fail("invalid", "Choose an active attendant.")
    if attendant.pk != request.membership.pk and "shifts.manage" not in effective_permissions(request.membership):
        fail("permission_denied", "You may only start your own shift.", 403)
    if "shifts.own" not in effective_permissions(attendant):
        fail("invalid", "This employee does not have shift access.")
    if scoped(Shift, request.tenant).filter(attendant=attendant, status="open").exists():
        fail("assignment_busy", "This attendant already has an open shift.")
    ids = data["nozzle_ids"]
    if len(set(ids)) != len(ids):
        fail("invalid", "Choose each nozzle once.")
    nozzles = [find(Nozzle, request.tenant, pk) for pk in ids]
    for nozzle in nozzles:
        require_ready_nozzle(nozzle)
        if scoped(NozzleAssignment, request.tenant).filter(nozzle=nozzle, is_active=True).exists():
            fail("assignment_busy", "A selected nozzle is assigned to another open shift.")
    shift = create(Shift, request, day=day, attendant=attendant, opening_cash=data["opening_cash"], reference=reference(Shift, request.tenant, "SHIFT"), notes=data.get("notes", ""))
    station = scoped(Station, request.tenant).get()
    tax = Decimal(station.settings.get("tax_rate", "0")) if station.settings.get("tax_enabled") else ZERO
    for nozzle in nozzles:
        create(NozzleAssignment, request, shift=shift, nozzle=nozzle, tank=nozzle.tank, product=nozzle.product, opening_meter=current_meter(request.tenant, nozzle), unit_price=nozzle.product.selling_price, tax_rate=tax)
    event(request, "shift_started", shift)
    return shift


def sale_quote(request, assignment, closing_meter):
    active_shift(request, assignment.shift)
    if not assignment.is_active:
        fail("assignment_busy", "This nozzle assignment has ended.")
    require_ready_nozzle(assignment.nozzle)
    opening = current_meter(request.tenant, assignment.nozzle)
    if closing_meter <= opening:
        fail("meter_invalid", "Closing meter must exceed the current meter.")
    liters = closing_meter - opening
    subtotal = money(liters * assignment.unit_price)
    tax = money(subtotal * assignment.tax_rate / Decimal("100"))
    return {"opening_meter": opening, "closing_meter": closing_meter, "liters": liters, "unit_price": assignment.unit_price, "subtotal": subtotal, "tax_rate": assignment.tax_rate, "tax_amount": tax, "total": subtotal + tax}


def post_sale(request, data):
    assignment = find(NozzleAssignment, request.tenant, data["assignment_id"])
    quote = sale_quote(request, assignment, data["closing_meter"])
    if quote["liters"] > stock(request.tenant, assignment.tank):
        fail("stock_insufficient", "The tank has insufficient book stock.")
    credit = data.get("credit_amount", ZERO)
    bank = data.get("bank_amount", ZERO)
    cash = data.get("cash_amount", quote["total"] - credit - bank)
    if min(credit, bank, cash) < ZERO or cash + bank + credit != quote["total"]:
        fail("payment_mismatch", "Cash, bank and credit must equal the calculated total.")
    customer = find(Customer, request.tenant, data["customer_id"]) if data.get("customer_id") else None
    if credit:
        if not customer or not customer.is_active:
            fail("credit_customer", "Choose an active credit customer.")
        if customer_balance(request.tenant, customer) + credit > customer.credit_limit:
            fail("credit_limit", "The customer's configured credit limit would be exceeded.")
    station = scoped(Station, request.tenant).get()
    snapshot = {"station_name": station.name, "address": station.address, "phone": station.phone, "header": station.receipt_header, "footer": station.receipt_footer, "width": station.settings.get("receipt_width", "80"), "product_name": assignment.product.name, "unit": assignment.product.unit, "nozzle_number": assignment.nozzle.number, "pump_name": assignment.nozzle.pump.name, "customer_name": customer.name if customer else "", "attendant_name": assignment.shift.attendant.user.username}
    reading = create(MeterReading, request, day=assignment.shift.day, assignment=assignment, opening_meter=quote["opening_meter"], closing_meter=quote["closing_meter"], liters=quote["liters"], notes=data.get("notes", ""))
    sale = create(FuelSale, request, day=assignment.shift.day, shift=assignment.shift, reading=reading, customer=customer, reference=reference(FuelSale, request.tenant, "SALE"), currency=station.currency, receipt_snapshot=snapshot, cash_amount=cash, bank_amount=bank, credit_amount=credit, unit_price=quote["unit_price"], subtotal=quote["subtotal"], tax_rate=quote["tax_rate"], tax_amount=quote["tax_amount"], total=quote["total"], notes=data.get("notes", ""))
    movement(request, InventoryMovement, day=sale.day, shift=sale.shift, tank=assignment.tank, sale=sale, kind="sale", quantity=-quote["liters"])
    movement(request, CashMovement, day=sale.day, shift=sale.shift, sale=sale, kind="sale", amount=cash)
    event(request, "sale_posted", sale, quote)
    return sale


def close_shift(request, shift, data):
    active_shift(request, shift)
    assignments = list(scoped(NozzleAssignment, request.tenant).filter(shift=shift, is_active=True))
    closing = data["closing_meters"]
    if set(closing) != {str(a.pk) for a in assignments}:
        fail("unsettled_meters", "Confirm the final reading for every assigned nozzle.")
    for assignment in assignments:
        value = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0).run_validation(closing[str(assignment.pk)])
        if value != current_meter(request.tenant, assignment.nozzle):
            fail("unsettled_meters", "Post any unrecorded liters before closing the shift.")
    expected = shift_cash(request.tenant, shift)
    difference = data["counted_cash"] - expected
    station = scoped(Station, request.tenant).get()
    threshold = Decimal(station.settings.get("cash_difference_threshold", "0"))
    if abs(difference) > threshold and ("shifts.manage" not in effective_permissions(request.membership) or not data.get("reason")):
        fail("cash_difference", "A manager must approve this cash difference with a reason.")
    shift.status = "closed"
    shift.expected_cash, shift.counted_cash, shift.cash_difference = expected, data["counted_cash"], difference
    shift.closed_at, shift.closed_by = timezone.now(), request.user
    shift.updated_by = request.user
    validated_save(shift)
    scoped(NozzleAssignment, request.tenant).filter(shift=shift).update(is_active=False, updated_by=request.user)
    event(request, "shift_closed", shift, {"expected_cash": expected, "counted_cash": shift.counted_cash, "difference": difference, "reason": data.get("reason", "")})
    return shift


def reopen_shift(request, shift, reason):
    require_open(shift.day)
    if shift.status != "closed":
        fail("invalid", "Only a closed shift can be reopened.")
    if not shift.attendant.is_active or not shift.attendant.user.is_active or "shifts.own" not in effective_permissions(shift.attendant):
        fail("invalid", "Choose an active attendant with shift access.")
    assignments = list(scoped(NozzleAssignment, request.tenant).filter(shift=shift))
    if scoped(Shift, request.tenant).filter(attendant=shift.attendant, status="open").exists():
        fail("assignment_busy", "This attendant already has another open shift.")
    for assignment in assignments:
        require_ready_nozzle(assignment.nozzle)
        if scoped(NozzleAssignment, request.tenant).filter(nozzle=assignment.nozzle, created_at__gt=assignment.created_at).exists():
            fail("latest_only", "Later nozzle assignments prevent reopening this shift.")
    event(request, "shift_reopened", shift, {"reason": reason, "previous_counted_cash": shift.counted_cash, "previous_difference": shift.cash_difference})
    shift.status = "open"
    shift.closed_at = shift.closed_by = shift.counted_cash = shift.expected_cash = shift.cash_difference = None
    shift.updated_by = request.user
    validated_save(shift)
    scoped(NozzleAssignment, request.tenant).filter(shift=shift).update(is_active=True, updated_by=request.user)
    return shift


def post_purchase(request, data):
    day = open_day(request)
    tank = find(Tank, request.tenant, data["tank_id"])
    supplier = find(Supplier, request.tenant, data["supplier_id"])
    if not tank.is_active or not tank.product.is_active or not supplier.is_active:
        fail("equipment_unavailable", "Choose an active tank, fuel and supplier.")
    if stock(request.tenant, tank) + data["quantity"] > tank.capacity:
        fail("tank_capacity", "The delivery would exceed tank capacity.")
    amount = money(data["quantity"] * data["unit_cost"])
    paid = data["paid_amount"]
    if paid > amount:
        fail("payment_mismatch", "Paid amount cannot exceed the purchase total.")
    if data["method"] == "cash" and paid > cash_balance(request.tenant):
        fail("cash_insufficient", "Record the opening cash/deposit before paying for this delivery.")
    purchase = create(FuelPurchase, request, day=day, tank=tank, product=tank.product, supplier=supplier, quantity=data["quantity"], unit_cost=data["unit_cost"], total=amount, paid_amount=paid, method=data["method"], reference=reference(FuelPurchase, request.tenant, "PURCHASE"), invoice_number=data.get("invoice_number", ""), notes=data.get("notes", ""))
    movement(request, InventoryMovement, day=day, tank=tank, purchase=purchase, kind="purchase", quantity=purchase.quantity)
    if purchase.method == "cash":
        movement(request, CashMovement, day=day, purchase=purchase, kind="purchase", amount=-paid)
    event(request, "purchase_posted", purchase)
    return purchase


def post_payment(request, data):
    customer = find(Customer, request.tenant, data["customer_id"])
    if data["amount"] > customer_balance(request.tenant, customer):
        fail("payment_mismatch", "Payment cannot exceed the outstanding customer balance.")
    shift = find(Shift, request.tenant, data["shift_id"]) if data.get("shift_id") else None
    if "customers.manage" not in effective_permissions(request.membership):
        shift = scoped(Shift, request.tenant).filter(attendant=request.membership, status="open").first()
        if not shift:
            fail("shift_required", "Start your shift before receiving a customer payment.")
    if shift:
        if "customers.manage" in effective_permissions(request.membership):
            require_open(shift.day)
            if shift.status != "open":
                fail("shift_closed", "Only an open shift can receive payments.")
        else:
            active_shift(request, shift)
        day = shift.day
    else:
        day = open_day(request)
    station = scoped(Station, request.tenant).get()
    snapshot = {"station_name": station.name, "address": station.address, "phone": station.phone, "header": station.receipt_header, "footer": station.receipt_footer, "width": station.settings.get("receipt_width", "80"), "customer_name": customer.name}
    payment = create(CustomerPayment, request, day=day, customer=customer, shift=shift, amount=data["amount"], method=data["method"], currency=station.currency, receipt_snapshot=snapshot, reference=reference(CustomerPayment, request.tenant, "PAYMENT"), notes=data.get("notes", ""))
    if payment.method == "cash":
        movement(request, CashMovement, day=day, shift=shift, customer_payment=payment, kind="customer_payment", amount=payment.amount)
    event(request, "customer_payment_posted", payment)
    return payment


def post_cash(request, data):
    day = open_day(request)
    shift = find(Shift, request.tenant, data["shift_id"]) if data.get("shift_id") else None
    if shift:
        require_open(shift.day)
        if shift.status != "open":
            fail("shift_closed", "Only an open shift can receive cash movements.")
        day = shift.day
    amount = data["amount"] if data["kind"] == "deposit" else -data["amount"]
    if amount < ZERO and -amount > cash_balance(request.tenant):
        fail("cash_insufficient", "Cash withdrawal exceeds the station cash balance.")
    if shift and amount < ZERO and -amount > shift_cash(request.tenant, shift):
        fail("cash_insufficient", "Cash withdrawal exceeds the shift drawer balance.")
    entry = create(CashMovement, request, day=day, shift=shift, amount=amount, kind=data["kind"], notes=data["reason"])
    event(request, "cash_" + entry.kind, entry)
    return entry


def post_physical(request, data):
    day = open_day(request)
    tank = find(Tank, request.tenant, data["tank_id"])
    if scoped(NozzleAssignment, request.tenant).filter(tank=tank, is_active=True).exists():
        fail("unsettled_meters", "Close the tank's shifts before measuring physical stock.")
    if data["measured_quantity"] > tank.capacity:
        fail("tank_capacity", "Physical stock cannot exceed tank capacity.")
    expected = stock(request.tenant, tank)
    variance = data["measured_quantity"] - expected
    if data["apply_adjustment"] and not data.get("reason"):
        fail("reason_required", "Stock adjustments require a reason.")
    reading = create(PhysicalStockReading, request, day=day, tank=tank, expected_quantity=expected, measured_quantity=data["measured_quantity"], variance=variance, adjustment_applied=data["apply_adjustment"], notes=data.get("reason", ""))
    if reading.adjustment_applied:
        movement(request, InventoryMovement, day=day, tank=tank, physical_reading=reading, kind="adjustment", quantity=variance, notes=reading.notes)
    event(request, "physical_stock_recorded", reading, {"variance": variance, "adjustment_applied": reading.adjustment_applied})
    return reading


def mark_reversed(request, record, reason):
    record.status, record.reversal_reason = "reversed", reason
    record.reversed_at, record.reversed_by, record.updated_by = timezone.now(), request.user, request.user
    validated_save(record)
    event(request, "reversed", record, {"reason": reason})


def reverse_sale(request, sale, reason):
    require_open(sale.day)
    if sale.status != "posted":
        fail("already_reversed", "This sale has already been reversed.")
    if sale.shift.status != "open":
        fail("shift_closed", "Reopen the shift before reversing its sale.")
    assignment = sale.reading.assignment
    latest = scoped(MeterReading, request.tenant).filter(assignment__nozzle=assignment.nozzle).order_by("-created_at", "-id").first()
    if latest.pk != sale.reading_id:
        fail("latest_only", "Only the latest erroneous nozzle reading can be reversed.")
    if sale.credit_amount and customer_balance(request.tenant, sale.customer) < sale.credit_amount:
        fail("payment_mismatch", "Reverse the customer's related payment before reversing this credit sale.")
    if stock(request.tenant, assignment.tank) + sale.reading.liters > assignment.tank.capacity:
        fail("tank_capacity", "Reversal would exceed tank capacity.")
    create(MeterReading, request, day=sale.day, assignment=assignment, opening_meter=sale.reading.closing_meter, closing_meter=sale.reading.opening_meter, liters=ZERO, kind="correction", notes=reason)
    movement(request, InventoryMovement, day=sale.day, shift=sale.shift, tank=assignment.tank, sale=sale, kind="reversal", quantity=sale.reading.liters, notes=reason)
    movement(request, CashMovement, day=sale.day, shift=sale.shift, sale=sale, kind="reversal", amount=-sale.cash_amount, notes=reason)
    mark_reversed(request, sale, reason)
    return sale


def reverse_purchase(request, purchase, reason):
    require_open(purchase.day)
    if purchase.status != "posted":
        fail("already_reversed", "This delivery has already been reversed.")
    if stock(request.tenant, purchase.tank) < purchase.quantity:
        fail("stock_insufficient", "Consumed stock prevents reversing this delivery.")
    movement(request, InventoryMovement, day=purchase.day, tank=purchase.tank, purchase=purchase, kind="reversal", quantity=-purchase.quantity, notes=reason)
    if purchase.method == "cash":
        movement(request, CashMovement, day=purchase.day, purchase=purchase, kind="reversal", amount=purchase.paid_amount, notes=reason)
    mark_reversed(request, purchase, reason)
    return purchase


def reverse_payment(request, payment, reason):
    require_open(payment.day)
    if payment.status != "posted":
        fail("already_reversed", "This customer payment has already been reversed.")
    if payment.shift_id and payment.shift.status != "open":
        fail("shift_closed", "Reopen the payment's shift before reversing it.")
    if payment.method == "cash":
        movement(request, CashMovement, day=payment.day, shift=payment.shift, customer_payment=payment, kind="reversal", amount=-payment.amount, notes=reason)
    mark_reversed(request, payment, reason)
    return payment


def day_snapshot(request, day):
    tenant = request.tenant
    sales = scoped(FuelSale, tenant).filter(day=day, status="posted")
    purchases = scoped(FuelPurchase, tenant).filter(day=day, status="posted")
    payments = scoped(CustomerPayment, tenant).filter(day=day, status="posted")
    movements = scoped(CashMovement, tenant).filter(day=day)
    tanks = []
    for tank in scoped(Tank, tenant).filter(is_active=True):
        reading = scoped(PhysicalStockReading, tenant).filter(tank=tank, day=day).order_by("-created_at").first()
        latest = scoped(InventoryMovement, tenant).filter(tank=tank).order_by("-created_at").first()
        if not reading or (latest and latest.created_at > reading.created_at and latest.physical_reading_id != reading.pk):
            fail("physical_required", "Record fresh physical stock for each active tank before closing.")
        tanks.append({"tank_id": str(tank.pk), "name": tank.name, "book_stock": stock(tenant, tank), "physical_stock": reading.measured_quantity, "variance": reading.variance})
    return {"sales_total": total(sales, "total"), "liters_sold": total(sales, "reading__liters"), "credit_sales": total(sales, "credit_amount"), "bank_sales": total(sales, "bank_amount"), "purchase_total": total(purchases, "total"), "supplier_due": total(purchases, "total")-total(purchases, "paid_amount"), "customer_payments": total(payments, "amount"), "cash_in": total(movements.filter(amount__gt=0), "amount"), "cash_out": -total(movements.filter(amount__lt=0), "amount"), "tanks": tanks}


def close_day(request, day, data):
    require_open(day)
    if scoped(Shift, request.tenant).filter(day=day, status="open").exists():
        fail("shifts_open", "Close every shift before closing the station day.")
    snapshot = day_snapshot(request, day)
    expected = cash_balance(request.tenant)
    difference = data["counted_cash"] - expected
    if difference and not data.get("reason"):
        fail("reason_required", "Explain the counted cash difference.")
    day.status, day.expected_cash, day.counted_cash, day.cash_difference = "closed", expected, data["counted_cash"], difference
    day.snapshot, day.notes = safe_json(snapshot), data.get("reason", "")
    day.closed_at, day.closed_by, day.updated_by = timezone.now(), request.user, request.user
    if difference:
        movement(request, CashMovement, day=day, kind="reconciliation", amount=difference, notes=data["reason"])
        day.snapshot["cash_adjustment"] = str(difference)
    validated_save(day)
    event(request, "day_closed", day, {"snapshot": snapshot, "difference": difference, "reason": day.notes})
    return day


def reopen_day(request, day, reason):
    if day.status != "closed" or scoped(DailyClosing, request.tenant).filter(business_date__gt=day.business_date).exists():
        fail("latest_only", "Only the latest closed station day can be reopened.")
    event(request, "day_reopened", day, {"reason": reason, "previous_snapshot": day.snapshot, "previous_counted_cash": day.counted_cash})
    day.status = "open"
    day.closed_at = day.closed_by = None
    day.snapshot = {}
    day.expected_cash = day.counted_cash = day.cash_difference = None
    day.notes = reason
    day.updated_by = request.user
    validated_save(day)
    return day

