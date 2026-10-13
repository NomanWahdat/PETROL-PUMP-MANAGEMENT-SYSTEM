from decimal import Decimal
from rest_framework import serializers
from apps.common.api import TenantSerializer
from apps.common.serializers import ExactDecimal
from apps.suppliers.models import Supplier
from apps.customers.models import Customer, CustomerPayment
from apps.shifts.models import Shift, NozzleAssignment
from apps.sales.models import FuelSale, MeterReading
from apps.purchases.models import FuelPurchase
from apps.inventory.models import InventoryMovement, PhysicalStockReading
from apps.cash.models import CashMovement, DailyClosing
from apps.tenants.permissions import effective_permissions
from . import services as ops


def cash(**kwargs):
    return ExactDecimal(max_digits=18, decimal_places=2, min_value=0, **kwargs)


def quantity(**kwargs):
    return ExactDecimal(max_digits=18, decimal_places=3, min_value=0, **kwargs)


class StartShiftInput(serializers.Serializer):
    attendant_id = serializers.UUIDField(required=False, allow_null=True)
    nozzle_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=50)
    opening_cash = cash(default=Decimal("0"))
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class SaleInput(serializers.Serializer):
    assignment_id = serializers.UUIDField()
    closing_meter = quantity()
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    cash_amount = cash(required=False)
    bank_amount = cash(default=Decimal("0"))
    credit_amount = cash(default=Decimal("0"))
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class CloseShiftInput(serializers.Serializer):
    closing_meters = serializers.DictField(child=quantity())
    counted_cash = cash()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=2000)


class CloseDayInput(serializers.Serializer):
    counted_cash = cash()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class PurchaseInput(serializers.Serializer):
    tank_id = serializers.UUIDField()
    supplier_id = serializers.UUIDField()
    quantity = ExactDecimal(max_digits=18, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = ExactDecimal(max_digits=18, decimal_places=4, min_value=0)
    paid_amount = cash(default=Decimal("0"))
    method = serializers.ChoiceField(choices=["cash", "bank"], default="cash")
    invoice_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class PaymentInput(serializers.Serializer):
    customer_id = serializers.UUIDField()
    shift_id = serializers.UUIDField(required=False, allow_null=True)
    amount = ExactDecimal(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    method = serializers.ChoiceField(choices=["cash", "bank"], default="cash")
    notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class CashInput(serializers.Serializer):
    shift_id = serializers.UUIDField(required=False, allow_null=True)
    amount = ExactDecimal(max_digits=18, decimal_places=2, min_value=Decimal("0.01"))
    kind = serializers.ChoiceField(choices=["deposit", "withdrawal"])
    reason = serializers.CharField(min_length=3, max_length=2000)


class PhysicalInput(serializers.Serializer):
    tank_id = serializers.UUIDField()
    measured_quantity = quantity()
    apply_adjustment = serializers.BooleanField(default=False)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class SupplierSerializer(TenantSerializer):
    balance = serializers.SerializerMethodField()
    class Meta:
        model = Supplier
        fields = ["id", "name", "code", "phone", "address", "is_active", "notes", "balance"]
        read_only_fields = ["id", "balance"]
        validators = []
    def get_balance(self, obj):
        if hasattr(obj, "outstanding"):
            return str(ops.money(obj.outstanding or Decimal("0")))
        query = ops.scoped(FuelPurchase, obj.tenant).filter(supplier=obj, status="posted")
        return str(ops.total(query, "total")-ops.total(query, "paid_amount"))


class CustomerSerializer(TenantSerializer):
    balance = serializers.SerializerMethodField()
    credit_limit = cash(required=False)
    opening_balance = cash(required=False)
    class Meta:
        model = Customer
        fields = ["id", "name", "code", "phone", "address", "credit_limit", "opening_balance", "is_active", "notes", "balance"]
        read_only_fields = ["id", "balance"]
        validators = []
    def get_balance(self, obj):
        if hasattr(obj, "posted_credit"):
            return str(ops.money(obj.opening_balance + (obj.posted_credit or Decimal("0")) - (obj.collected or Decimal("0"))))
        return str(ops.customer_balance(obj.tenant, obj))
    def validate(self, attrs):
        if self.instance and "opening_balance" in attrs and attrs["opening_balance"] != self.instance.opening_balance:
            raise serializers.ValidationError({"opening_balance": "Opening debt is immutable. Record payments or reverse transactions."})
        limit = attrs.get("credit_limit", self.instance.credit_limit if self.instance else Decimal("0"))
        balance = ops.customer_balance(self.instance.tenant, self.instance) if self.instance else attrs.get("opening_balance", Decimal("0"))
        if limit < balance:
            raise serializers.ValidationError({"credit_limit": "Credit limit cannot be below outstanding debt."})
        return attrs
    def to_representation(self, instance):
        if "operation_permissions" not in self.context:
            self.context["operation_permissions"] = effective_permissions(self.context["request"].membership)
        permissions = self.context["operation_permissions"]
        if "customers.manage" not in permissions and "reports.operational" not in permissions:
            return {"id": str(instance.pk), "name": instance.name, "phone": instance.phone, "is_active": instance.is_active}
        return super().to_representation(instance)


class AssignmentSerializer(serializers.ModelSerializer):
    nozzle_label = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name")
    current_meter = serializers.SerializerMethodField()
    class Meta:
        model = NozzleAssignment
        fields = ["id", "nozzle", "nozzle_label", "tank", "product_name", "opening_meter", "current_meter", "unit_price", "tax_rate", "is_active"]
    def get_nozzle_label(self, obj):
        return f"{obj.nozzle.pump.name} / {obj.nozzle.number}"
    def get_current_meter(self, obj):
        if hasattr(obj, "latest_meter"):
            return str(obj.latest_meter if obj.latest_meter is not None else obj.nozzle.opening_meter)
        return str(ops.current_meter(obj.tenant, obj.nozzle))


class ShiftSerializer(serializers.ModelSerializer):
    assignments = AssignmentSerializer(many=True, read_only=True)
    attendant_name = serializers.SerializerMethodField()
    business_date = serializers.DateField(source="day.business_date")
    current_expected_cash = serializers.SerializerMethodField()
    class Meta:
        model = Shift
        fields = ["id", "reference", "day", "business_date", "attendant", "attendant_name", "status", "opening_cash", "expected_cash", "current_expected_cash", "counted_cash", "cash_difference", "created_at", "closed_at", "assignments", "notes"]
    def get_attendant_name(self, obj):
        employee = getattr(obj.attendant, "employee", None)
        return employee.name if employee else obj.attendant.user.username
    def get_current_expected_cash(self, obj):
        if hasattr(obj, "drawer_movements"):
            return str(ops.money(obj.opening_cash + (obj.drawer_movements or Decimal("0"))))
        return str(ops.shift_cash(obj.tenant, obj))


class SaleSerializer(serializers.ModelSerializer):
    liters = serializers.DecimalField(source="reading.liters", max_digits=18, decimal_places=3)
    opening_meter = serializers.DecimalField(source="reading.opening_meter", max_digits=18, decimal_places=3)
    closing_meter = serializers.DecimalField(source="reading.closing_meter", max_digits=18, decimal_places=3)
    business_date = serializers.DateField(source="day.business_date")
    class Meta:
        model = FuelSale
        fields = ["id", "reference", "shift", "business_date", "reading", "customer", "liters", "opening_meter", "closing_meter", "unit_price", "subtotal", "tax_rate", "tax_amount", "total", "cash_amount", "bank_amount", "credit_amount", "currency", "receipt_snapshot", "status", "created_at", "created_by", "reversed_at", "reversal_reason", "notes"]


def read_serializer(model, fields, labels=None):
    attrs = {"Meta": type("Meta", (), {"model": model, "fields": fields})}
    for key, source in (labels or {}).items():
        attrs[key] = serializers.CharField(source=source, read_only=True)
    return type(model.__name__+"Serializer", (serializers.ModelSerializer,), attrs)


PurchaseSerializer = read_serializer(FuelPurchase, ["id", "reference", "day", "supplier", "supplier_name", "tank", "tank_name", "quantity", "unit_cost", "total", "paid_amount", "method", "invoice_number", "status", "created_at", "created_by", "reversal_reason", "notes"], {"supplier_name": "supplier.name", "tank_name": "tank.name"})
PaymentSerializer = read_serializer(CustomerPayment, ["id", "reference", "day", "customer", "customer_name", "shift", "amount", "method", "currency", "receipt_snapshot", "status", "created_at", "created_by", "reversal_reason", "notes"], {"customer_name": "customer.name"})
MeterSerializer = read_serializer(MeterReading, ["id", "day", "assignment", "nozzle_label", "opening_meter", "closing_meter", "liters", "kind", "created_at", "created_by", "notes"], {"nozzle_label": "assignment.nozzle.number"})
InventorySerializer = read_serializer(InventoryMovement, ["id", "day", "tank", "tank_name", "shift", "sale", "purchase", "physical_reading", "kind", "quantity", "created_at", "created_by", "notes"], {"tank_name": "tank.name"})
PhysicalSerializer = read_serializer(PhysicalStockReading, ["id", "day", "tank", "tank_name", "expected_quantity", "measured_quantity", "variance", "adjustment_applied", "created_at", "created_by", "notes"], {"tank_name": "tank.name"})
CashSerializer = read_serializer(CashMovement, ["id", "day", "shift", "sale", "purchase", "customer_payment", "kind", "amount", "created_at", "created_by", "notes"])
DaySerializer = read_serializer(DailyClosing, ["id", "business_date", "status", "opening_cash", "expected_cash", "counted_cash", "cash_difference", "snapshot", "closed_at", "created_at", "notes"])

