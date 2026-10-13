from django.db import models
from apps.operations.models import DayRecord
from apps.common.decimal_constraints import DecimalEquality


class MeterReading(DayRecord):
    assignment = models.ForeignKey("shifts.NozzleAssignment", on_delete=models.PROTECT)
    opening_meter = models.DecimalField(max_digits=18, decimal_places=3)
    closing_meter = models.DecimalField(max_digits=18, decimal_places=3)
    liters = models.DecimalField(max_digits=18, decimal_places=3)
    kind = models.CharField(max_length=12, choices=[("sale", "Sale"), ("correction", "Correction")], default="sale")
    class Meta(DayRecord.Meta):
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["tenant", "assignment", "-created_at"], name="meter_tenant_assignment_time")]
        constraints = DayRecord.Meta.constraints + [
            models.CheckConstraint(condition=models.Q(opening_meter__gte=0, closing_meter__gte=0, liters__gte=0), name="meter_nonnegative"),
            models.CheckConstraint(condition=models.Q(kind="correction", liters=0) | (models.Q(kind="sale", liters__gt=0) & DecimalEquality(models.F("liters"), models.F("closing_meter")-models.F("opening_meter"), 3)), name="meter_difference"),
        ]


class FuelSale(DayRecord):
    shift = models.ForeignKey("shifts.Shift", on_delete=models.PROTECT)
    reading = models.OneToOneField(MeterReading, on_delete=models.PROTECT)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True)
    reference = models.CharField(max_length=30)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    subtotal = models.DecimalField(max_digits=18, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    cash_amount = models.DecimalField(max_digits=18, decimal_places=2)
    bank_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=3)
    receipt_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default="posted", choices=[("posted", "Posted"), ("reversed", "Reversed")])
    reversal_reason = models.TextField(blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_sales")
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "day", "status"], name="sale_tenant_day_status"),
                   models.Index(fields=["tenant", "customer", "status"], name="sale_tenant_customer_status")]
        constraints = DayRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["tenant", "reference"], name="sale_reference"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0, total__gte=0, cash_amount__gte=0, bank_amount__gte=0, credit_amount__gte=0), name="sale_nonnegative"),
            models.CheckConstraint(condition=DecimalEquality(models.F("total"), models.F("cash_amount")+models.F("bank_amount")+models.F("credit_amount"), 2), name="sale_allocation"),
            models.CheckConstraint(condition=DecimalEquality(models.F("total"), models.F("subtotal")+models.F("tax_amount"), 2) & models.Q(subtotal__gte=0, tax_amount__gte=0, tax_rate__gte=0, tax_rate__lte=100), name="sale_tax_values"),
            models.CheckConstraint(condition=models.Q(credit_amount=0) | models.Q(customer__isnull=False), name="sale_credit_customer"),
        ]

