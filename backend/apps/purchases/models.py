from django.db import models
from apps.operations.models import DayRecord


class FuelPurchase(DayRecord):
    supplier = models.ForeignKey("suppliers.Supplier", on_delete=models.PROTECT)
    tank = models.ForeignKey("fuel.Tank", on_delete=models.PROTECT)
    product = models.ForeignKey("fuel.FuelProduct", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=4)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    method = models.CharField(max_length=10, choices=[("cash", "Cash"), ("bank", "Bank")], default="cash")
    reference = models.CharField(max_length=30)
    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=12, default="posted", choices=[("posted", "Posted"), ("reversed", "Reversed")])
    reversal_reason = models.TextField(blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_purchases")
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "supplier", "status"], name="purchase_tenant_supplier_state")]
        constraints = DayRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["tenant", "reference"], name="purchase_reference"),
            models.UniqueConstraint(fields=["tenant", "supplier", "invoice_number"], condition=~models.Q(invoice_number=""), name="supplier_invoice_once"),
            models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_cost__gte=0, total__gte=0, paid_amount__gte=0, paid_amount__lte=models.F("total")), name="purchase_values"),
        ]

