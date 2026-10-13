from django.db import models
from apps.operations.models import ScopedRecord, DayRecord


class DailyClosing(ScopedRecord):
    business_date = models.DateField()
    status = models.CharField(max_length=10, choices=[("open", "Open"), ("closed", "Closed")], default="open")
    opening_cash = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cash_difference = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="closed_days")
    class Meta(ScopedRecord.Meta):
        constraints = ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["tenant", "business_date"], name="one_station_day"),
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(status="open"), name="one_open_station_day"),
        ]


class CashMovement(DayRecord):
    shift = models.ForeignKey("shifts.Shift", on_delete=models.PROTECT, null=True, blank=True)
    sale = models.ForeignKey("sales.FuelSale", on_delete=models.PROTECT, null=True, blank=True)
    purchase = models.ForeignKey("purchases.FuelPurchase", on_delete=models.PROTECT, null=True, blank=True)
    customer_payment = models.ForeignKey("customers.CustomerPayment", on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=20, choices=[("sale", "Sale"), ("purchase", "Purchase"), ("customer_payment", "Customer payment"), ("deposit", "Deposit"), ("withdrawal", "Withdrawal"), ("reversal", "Reversal"), ("reconciliation", "Count reconciliation")])
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "shift", "-created_at"], name="cash_tenant_shift_time")]
        constraints = DayRecord.Meta.constraints + [models.CheckConstraint(condition=~models.Q(amount=0), name="cash_movement_nonzero")]

