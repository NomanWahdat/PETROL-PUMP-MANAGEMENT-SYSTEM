from django.db import models
from apps.operations.models import DayRecord, ScopedRecord


class Shift(DayRecord):
    attendant = models.ForeignKey("tenants.Membership", on_delete=models.PROTECT)
    reference = models.CharField(max_length=30)
    status = models.CharField(max_length=10, choices=[("open", "Open"), ("closed", "Closed")], default="open")
    opening_cash = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    counted_cash = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    cash_difference = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="closed_shifts")
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "status", "-created_at"], name="shift_tenant_status_time")]
        constraints = DayRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["tenant", "reference"], name="shift_reference"),
            models.UniqueConstraint(fields=["attendant"], condition=models.Q(status="open"), name="one_open_attendant_shift"),
            models.CheckConstraint(condition=models.Q(opening_cash__gte=0), name="shift_opening_cash_nonnegative"),
        ]


class NozzleAssignment(ScopedRecord):
    shift = models.ForeignKey(Shift, on_delete=models.PROTECT, related_name="assignments")
    nozzle = models.ForeignKey("fuel.Nozzle", on_delete=models.PROTECT)
    tank = models.ForeignKey("fuel.Tank", on_delete=models.PROTECT)
    product = models.ForeignKey("fuel.FuelProduct", on_delete=models.PROTECT)
    opening_meter = models.DecimalField(max_digits=18, decimal_places=3)
    unit_price = models.DecimalField(max_digits=18, decimal_places=4)
    tax_rate = models.DecimalField(max_digits=7, decimal_places=4, default=0)
    is_active = models.BooleanField(default=True)
    class Meta(ScopedRecord.Meta):
        indexes = [models.Index(fields=["tenant", "nozzle", "-created_at"], name="assignment_tenant_nozzle_time")]
        constraints = ScopedRecord.Meta.constraints + [
            models.UniqueConstraint(fields=["shift", "nozzle"], name="shift_nozzle_once"),
            models.UniqueConstraint(fields=["nozzle"], condition=models.Q(is_active=True), name="one_active_nozzle_assignment"),
            models.CheckConstraint(condition=models.Q(opening_meter__gte=0, unit_price__gte=0), name="assignment_nonnegative"),
        ]

