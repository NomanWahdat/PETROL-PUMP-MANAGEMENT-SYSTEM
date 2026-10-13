from django.db import models
from apps.operations.models import ScopedRecord, DayRecord


class Customer(ScopedRecord):
    name = models.CharField(max_length=150)
    code = models.SlugField(max_length=40)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["tenant", "code"], name="customer_code"),
            models.CheckConstraint(condition=models.Q(credit_limit__gte=0, opening_balance__gte=0), name="customer_nonnegative"),
        ]


class CustomerPayment(DayRecord):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    shift = models.ForeignKey("shifts.Shift", on_delete=models.PROTECT, null=True, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    method = models.CharField(max_length=10, choices=[("cash", "Cash"), ("bank", "Bank")], default="cash")
    reference = models.CharField(max_length=30)
    currency = models.CharField(max_length=3, default="AFN")
    receipt_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, default="posted", choices=[("posted", "Posted"), ("reversed", "Reversed")])
    reversal_reason = models.TextField(blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_payments")
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "customer", "status"], name="payment_tenant_customer_status")]
        constraints = DayRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["tenant", "reference"], name="payment_reference"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="payment_positive"),
        ]

