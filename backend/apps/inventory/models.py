from django.db import models
from apps.operations.models import DayRecord
from apps.common.decimal_constraints import DecimalEquality


class PhysicalStockReading(DayRecord):
    tank = models.ForeignKey("fuel.Tank", on_delete=models.PROTECT)
    expected_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    measured_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    variance = models.DecimalField(max_digits=18, decimal_places=3)
    adjustment_applied = models.BooleanField(default=False)
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "tank", "-created_at"], name="physical_tenant_tank_time")]
        constraints = DayRecord.Meta.constraints + [
            models.CheckConstraint(condition=models.Q(measured_quantity__gte=0), name="physical_quantity_nonnegative"),
            models.CheckConstraint(condition=DecimalEquality(models.F("variance"), models.F("measured_quantity")-models.F("expected_quantity"), 3), name="physical_variance"),
        ]


class InventoryMovement(DayRecord):
    tank = models.ForeignKey("fuel.Tank", on_delete=models.PROTECT)
    shift = models.ForeignKey("shifts.Shift", on_delete=models.PROTECT, null=True, blank=True)
    sale = models.ForeignKey("sales.FuelSale", on_delete=models.PROTECT, null=True, blank=True)
    purchase = models.ForeignKey("purchases.FuelPurchase", on_delete=models.PROTECT, null=True, blank=True)
    physical_reading = models.ForeignKey(PhysicalStockReading, on_delete=models.PROTECT, null=True, blank=True)
    kind = models.CharField(max_length=15, choices=[("sale", "Sale"), ("purchase", "Purchase"), ("reversal", "Reversal"), ("adjustment", "Adjustment")])
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    class Meta(DayRecord.Meta):
        indexes = [models.Index(fields=["tenant", "tank", "-created_at"], name="stock_tenant_tank_time")]
        constraints = DayRecord.Meta.constraints + [models.CheckConstraint(condition=~models.Q(quantity=0), name="movement_nonzero")]

