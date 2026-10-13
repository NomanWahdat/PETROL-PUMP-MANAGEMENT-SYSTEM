from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.common.models import TenantOwnedModel


class FuelProduct(TenantOwnedModel):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=30)
    unit = models.CharField(max_length=30, default="liter")
    purchase_price = models.DecimalField(max_digits=18, decimal_places=4, default=0, validators=[MinValueValidator(0)])
    selling_price = models.DecimalField(max_digits=18, decimal_places=4, default=0, validators=[MinValueValidator(0)])
    minimum_stock = models.DecimalField(max_digits=18, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_fuel_code"),
            models.UniqueConstraint(fields=["tenant", "id"], name="fuel_tenant_id"),
            models.CheckConstraint(condition=models.Q(purchase_price__gte=0, selling_price__gte=0, minimum_stock__gte=0), name="nonnegative_fuel_values"),
        ]


class FuelPriceHistory(TenantOwnedModel):
    product = models.ForeignKey(FuelProduct, on_delete=models.PROTECT)
    purchase_price = models.DecimalField(max_digits=18, decimal_places=4)
    selling_price = models.DecimalField(max_digits=18, decimal_places=4)
    reason = models.CharField(max_length=250, blank=True)

    class Meta(TenantOwnedModel.Meta):
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "product", "created_at"], name="fuel_price_time")]
        constraints = [models.CheckConstraint(condition=models.Q(purchase_price__gte=0, selling_price__gte=0), name="nonnegative_history_prices")]


class Tank(TenantOwnedModel):
    name = models.CharField(max_length=100)
    product = models.ForeignKey(FuelProduct, on_delete=models.PROTECT)
    capacity = models.DecimalField(max_digits=18, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    opening_quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    minimum_stock = models.DecimalField(max_digits=18, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def clean(self):
        self.validate_tenant_links("product")

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_tank_name"),
            models.UniqueConstraint(fields=["tenant", "id"], name="tank_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "id", "product"], name="tank_tenant_product"),
            models.CheckConstraint(condition=models.Q(capacity__gt=0, opening_quantity__gte=0, minimum_stock__gte=0, opening_quantity__lte=models.F("capacity"), minimum_stock__lte=models.F("capacity")), name="valid_tank_quantities"),
        ]


class Pump(TenantOwnedModel):
    name = models.CharField(max_length=100)
    number = models.CharField(max_length=30)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=[("ready", "Ready"), ("maintenance", "Maintenance")], default="ready")
    is_active = models.BooleanField(default=True)

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_pump_number"),
            models.UniqueConstraint(fields=["tenant", "id"], name="pump_tenant_id"),
            models.CheckConstraint(condition=models.Q(status__in=["ready", "maintenance"]), name="valid_pump_status"),
        ]


class Nozzle(TenantOwnedModel):
    number = models.CharField(max_length=30)
    pump = models.ForeignKey(Pump, on_delete=models.PROTECT)
    product = models.ForeignKey(FuelProduct, on_delete=models.PROTECT)
    tank = models.ForeignKey(Tank, on_delete=models.PROTECT, null=True, blank=True)
    opening_meter = models.DecimalField(max_digits=18, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    def clean(self):
        self.validate_tenant_links("pump", "product", "tank")
        if self.tank_id and self.tank.product_id != self.product_id:
            raise ValidationError({"tank": "Tank and nozzle must use the same fuel product."})

    class Meta(TenantOwnedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="nozzle_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "pump", "number"], name="unique_nozzle_number"),
            models.CheckConstraint(condition=models.Q(opening_meter__gte=0), name="nonnegative_nozzle_meter"),
        ]
