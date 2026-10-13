from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.db.models import Prefetch, Sum, Subquery, OuterRef
from rest_framework import filters, mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.api import TenantViewSet
from apps.tenants.permissions import HasTenantPermission, effective_permissions
from apps.employees.models import Employee
from apps.fuel.models import Nozzle, Tank
from apps.shifts.models import Shift, NozzleAssignment
from apps.sales.models import MeterReading, FuelSale
from apps.purchases.models import FuelPurchase
from apps.customers.models import CustomerPayment
from apps.cash.models import CashMovement
from apps.customers.models import Customer
from apps.suppliers.models import Supplier
from apps.inventory.models import PhysicalStockReading
from apps.cash.models import DailyClosing
from . import services as ops
from .serializers import (SupplierSerializer, CustomerSerializer, ShiftSerializer, SaleSerializer,
    PurchaseSerializer, PaymentSerializer, MeterSerializer, InventorySerializer, PhysicalSerializer,
    CashSerializer, DaySerializer, StartShiftInput, SaleInput, CloseShiftInput, ReasonInput,
    CloseDayInput, PurchaseInput, PaymentInput, CashInput, PhysicalInput)


class SupplierViewSet(TenantViewSet):
    serializer_class = SupplierSerializer
    read_permission = ("reports.operational", "purchases.manage")
    write_permission = "purchases.manage"
    search_fields = ["name", "code", "phone"]

    def get_queryset(self):
        purchases = ops.scoped(FuelPurchase, self.request.tenant).filter(supplier_id=OuterRef("pk"), status="posted").values("supplier_id").annotate(due=Sum("total")-Sum("paid_amount"))
        return super().get_queryset().annotate(outstanding=Subquery(purchases.values("due")[:1]))


class CustomerViewSet(TenantViewSet):
    serializer_class = CustomerSerializer
    read_permission = ("reports.operational", "shifts.own", "customers.manage")
    write_permission = "customers.manage"
    search_fields = ["name", "code", "phone"]

    def get_queryset(self):
        sales = ops.scoped(FuelSale, self.request.tenant).filter(customer_id=OuterRef("pk"), status="posted").values("customer_id").annotate(value=Sum("credit_amount"))
        payments = ops.scoped(CustomerPayment, self.request.tenant).filter(customer_id=OuterRef("pk"), status="posted").values("customer_id").annotate(value=Sum("amount"))
        return super().get_queryset().annotate(posted_credit=Subquery(sales.values("value")[:1]), collected=Subquery(payments.values("value")[:1]))


@method_decorator(never_cache, name="dispatch")
class OperationalViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [HasTenantPermission]
    http_method_names = ["get", "post", "head", "options"]
    filter_backends = [filters.SearchFilter]
    search_fields = ["reference"]
    read_permission = "reports.operational"
    write_permission = "shifts.manage"
    own_filter = None
    unrestricted_read_permissions = ("reports.operational", "shifts.manage")
    related = ()

    def get_required_permission(self, request):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            read = self.read_permission if isinstance(self.read_permission, tuple) else (self.read_permission,)
            return (*read, "shifts.own") if self.own_filter else read
        if self.action in {"reverse", "reopen"}:
            return self.reversal_permission
        return self.write_permission

    def get_queryset(self):
        query = ops.scoped(self.serializer_class.Meta.model, self.request.tenant).select_related("tenant", *self.related).order_by("-created_at", "-id")
        permissions = effective_permissions(self.request.membership)
        if self.own_filter and not any(value in permissions for value in self.unrestricted_read_permissions):
            query = query.filter(**{self.own_filter: self.request.membership.pk})
        if self.request.query_params.get("status") and hasattr(self.serializer_class.Meta.model, "status"):
            status = serializers.ChoiceField(choices=self.serializer_class.Meta.model._meta.get_field("status").choices).run_validation(self.request.query_params["status"])
            query = query.filter(status=status)
        day = self.request.query_params.get("day")
        if day:
            query = query.filter(day_id=serializers.UUIDField().run_validation(day))
        return query

    def input(self, cls):
        serializer = cls(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def post_operation(self, operation, callback):
        result = ops.execute(self.request, operation, self.get_required_permission(self.request), lambda: self.get_serializer(callback()).data)
        return Response(result)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        record = self.get_object()
        reason = self.input(ReasonInput)["reason"]
        return self.post_operation(self.basename+".reverse."+str(record.pk), lambda: self.reverse_service(request, ops.find(self.serializer_class.Meta.model, request.tenant, record.pk), reason))


class ShiftViewSet(OperationalViewSet):
    serializer_class = ShiftSerializer
    own_filter = "attendant_id"
    write_permission = ("shifts.own", "shifts.manage")
    reversal_permission = "shifts.manage"
    read_permission = ("reports.operational", "shifts.manage")
    related = ("day", "attendant__user", "attendant__employee")
    reverse = None  # Shift closure/reopening preserves readings; shifts cannot be cancelled/deleted.

    def get_queryset(self):
        readings = ops.scoped(MeterReading, self.request.tenant).filter(assignment__nozzle_id=OuterRef("nozzle_id")).order_by("-created_at", "-id")
        assignments = ops.scoped(NozzleAssignment, self.request.tenant).select_related("tenant", "nozzle__pump", "product").annotate(latest_meter=Subquery(readings.values("closing_meter")[:1]))
        return super().get_queryset().prefetch_related(Prefetch("assignments", queryset=assignments)).annotate(drawer_movements=Sum("cashmovement__amount"))

    def create(self, request):
        data = self.input(StartShiftInput)
        return self.post_operation("shift.start", lambda: ops.start_shift(request, data))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        shift = self.get_object()
        data = self.input(CloseShiftInput)
        return self.post_operation("shift.close."+str(shift.pk), lambda: ops.close_shift(request, ops.find(Shift, request.tenant, shift.pk), data))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        shift = self.get_object()
        reason = self.input(ReasonInput)["reason"]
        return self.post_operation("shift.reopen."+str(shift.pk), lambda: ops.reopen_shift(request, ops.find(Shift, request.tenant, shift.pk), reason))


class SaleViewSet(OperationalViewSet):
    serializer_class = SaleSerializer
    own_filter = "shift__attendant_id"
    write_permission = ("shifts.own", "shifts.manage")
    reversal_permission = "shifts.manage"
    read_permission = ("reports.operational", "shifts.manage")
    related = ("reading", "day")
    reverse_service = staticmethod(ops.reverse_sale)

    def create(self, request):
        data = self.input(SaleInput)
        return self.post_operation("sale.post", lambda: ops.post_sale(request, data))

    @action(detail=False, methods=["post"])
    def quote(self, request):
        data = self.input(SaleInput)
        assignment = ops.find(NozzleAssignment, request.tenant, data["assignment_id"])
        quote = ops.sale_quote(request, assignment, data["closing_meter"])
        cash_amount = quote["total"]-data["credit_amount"]-data["bank_amount"]
        if cash_amount < 0:
            ops.fail("payment_mismatch", "Bank and credit cannot exceed the sale total.")
        return Response(ops.safe_json({**quote, "cash_amount": cash_amount}))

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        sale = self.get_object()
        return Response(self.get_serializer(sale).data)


class PurchaseViewSet(OperationalViewSet):
    serializer_class = PurchaseSerializer
    write_permission = reversal_permission = "purchases.manage"
    read_permission = ("reports.operational", "purchases.manage")
    related = ("supplier", "tank")
    reverse_service = staticmethod(ops.reverse_purchase)
    def create(self, request):
        data = self.input(PurchaseInput)
        return self.post_operation("purchase.post", lambda: ops.post_purchase(request, data))


class PaymentViewSet(OperationalViewSet):
    serializer_class = PaymentSerializer
    own_filter = "shift__attendant_id"
    write_permission = ("customers.manage", "shifts.own")
    reversal_permission = "customers.manage"
    read_permission = ("reports.operational", "customers.manage")
    unrestricted_read_permissions = ("reports.operational", "shifts.manage", "customers.manage")
    related = ("customer",)
    reverse_service = staticmethod(ops.reverse_payment)
    def create(self, request):
        data = self.input(PaymentInput)
        return self.post_operation("payment.post", lambda: ops.post_payment(request, data))
    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        return Response(self.get_serializer(self.get_object()).data)


class MeterViewSet(OperationalViewSet):
    serializer_class = MeterSerializer
    own_filter = "assignment__shift__attendant_id"
    read_permission = ("reports.operational", "shifts.manage")
    related = ("assignment__nozzle",)
    search_fields = []
    http_method_names = ["get", "head", "options"]
    reverse = None


class InventoryViewSet(OperationalViewSet):
    serializer_class = InventorySerializer
    search_fields = ["tank__name"]
    read_permission = ("reports.operational", "inventory.manage")
    related = ("tank",)
    http_method_names = ["get", "head", "options"]
    reverse = None


class PhysicalViewSet(OperationalViewSet):
    serializer_class = PhysicalSerializer
    search_fields = ["tank__name"]
    write_permission = "inventory.manage"
    read_permission = ("reports.operational", "inventory.manage")
    related = ("tank",)
    reverse = None
    def create(self, request):
        data = self.input(PhysicalInput)
        return self.post_operation("physical.post", lambda: ops.post_physical(request, data))


class CashViewSet(OperationalViewSet):
    serializer_class = CashSerializer
    search_fields = ["kind", "notes"]
    write_permission = "cash.manage"
    read_permission = ("reports.operational", "cash.manage")
    reverse = None
    def create(self, request):
        data = self.input(CashInput)
        return self.post_operation("cash.post", lambda: ops.post_cash(request, data))


class DayViewSet(OperationalViewSet):
    serializer_class = DaySerializer
    search_fields = []
    write_permission = reversal_permission = "closing.manage"
    read_permission = ("reports.operational", "closing.manage")
    reverse = None
    def get_queryset(self):
        # DailyClosing is the day itself, rather than a day-owned ledger.
        query = ops.scoped(DailyClosing, self.request.tenant).order_by("-business_date")
        if self.request.query_params.get("status"):
            status = serializers.ChoiceField(choices=DailyClosing._meta.get_field("status").choices).run_validation(self.request.query_params["status"])
            query = query.filter(status=status)
        return query
    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        day = self.get_object()
        data = self.input(CloseDayInput)
        return self.post_operation("day.close."+str(day.pk), lambda: ops.close_day(request, ops.find(DailyClosing, request.tenant, day.pk), data))
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        day = self.get_object()
        reason = self.input(ReasonInput)["reason"]
        return self.post_operation("day.reopen."+str(day.pk), lambda: ops.reopen_day(request, ops.find(DailyClosing, request.tenant, day.pk), reason))


@method_decorator(never_cache, name="dispatch")
class OperationsOptionsView(APIView):
    permission_classes = [HasTenantPermission]
    required_permission = ("shifts.own", "shifts.manage", "reports.operational", "customers.manage", "purchases.manage", "inventory.manage", "cash.manage", "closing.manage")
    def get(self, request):
        tenant = request.tenant
        permissions = effective_permissions(request.membership)
        nozzles = []
        if "shifts.own" in permissions or "shifts.manage" in permissions:
            busy = ops.scoped(NozzleAssignment, tenant).filter(is_active=True).values_list("nozzle_id", flat=True)
            for nozzle in ops.scoped(Nozzle, tenant).filter(is_active=True, pump__is_active=True, pump__status="ready", product__is_active=True, tank__is_active=True).exclude(pk__in=busy).select_related("pump", "product", "tank"):
                nozzles.append({"id": str(nozzle.pk), "label": f"{nozzle.pump.name} / {nozzle.number} / {nozzle.product.name}", "meter": str(ops.current_meter(tenant, nozzle))})
        customer_choices = list(ops.scoped(Customer, tenant).filter(is_active=True).values("id", "name", "phone")) if any(value in permissions for value in ("reports.operational", "customers.manage", "shifts.own", "shifts.manage")) else []
        result = {"nozzles": nozzles, "customers": customer_choices}
        if "shifts.manage" in permissions:
            result["attendants"] = [{"id": str(e.membership_id), "name": e.name} for e in ops.scoped(Employee, tenant).filter(membership__is_active=True, membership__user__is_active=True).select_related("membership") if "shifts.own" in effective_permissions(e.membership)]
        if any(value in permissions for value in ("reports.operational", "cash.manage", "customers.manage", "shifts.manage")):
            result["open_shifts"] = [{"id": str(shift.pk), "label": f"{shift.reference} / {shift.attendant.user.username}"} for shift in ops.scoped(Shift, tenant).filter(status="open").select_related("attendant__user")]
        if any(value in permissions for value in ("reports.operational", "inventory.manage", "purchases.manage")):
            tanks = []
            for tank in ops.scoped(Tank, tenant).filter(is_active=True).select_related("product"):
                physical = ops.scoped(PhysicalStockReading, tenant).filter(tank=tank).select_related("tank").order_by("-created_at", "-id").first()
                tanks.append({"id": str(tank.pk), "name": tank.name, "product_name": tank.product.name, "capacity": str(tank.capacity), "book_stock": str(ops.stock(tenant, tank)), "minimum_stock": str(tank.minimum_stock), "latest_physical": PhysicalSerializer(physical).data if physical else None})
            result["tanks"] = tanks
        if "reports.operational" in permissions or "purchases.manage" in permissions:
            result["suppliers"] = list(ops.scoped(Supplier, tenant).filter(is_active=True).values("id", "name"))
        if "reports.operational" in permissions or "cash.manage" in permissions:
            result["cash_balance"] = str(ops.cash_balance(tenant))
        if "reports.operational" in permissions or "closing.manage" in permissions:
            day = ops.scoped(DailyClosing, tenant).order_by("-business_date").first()
            result["day"] = DaySerializer(day).data if day else None
        return Response(ops.safe_json(result))

