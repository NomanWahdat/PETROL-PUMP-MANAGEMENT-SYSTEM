from rest_framework import serializers

from apps.common.api import TenantSerializer
from .models import FuelPriceHistory, FuelProduct, Nozzle, Pump, Tank


class FuelProductSerializer(TenantSerializer):
    price_reason = serializers.CharField(write_only=True, required=False, max_length=250, allow_blank=True)

    class Meta:
        model = FuelProduct
        fields = ["id", "name", "code", "unit", "purchase_price", "selling_price", "minimum_stock", "is_active", "notes", "price_reason"]
        read_only_fields = ["id"]
        validators = []

    def validate(self, attrs):
        if self.instance:
            tenant = self.context["request"].tenant
            tanks = Tank.objects.for_tenant(tenant).filter(product=self.instance)
            nozzles = Nozzle.objects.for_tenant(tenant).filter(product=self.instance)
            if attrs.get("unit", self.instance.unit) != self.instance.unit and (tanks.exists() or nozzles.exists()):
                raise serializers.ValidationError({"unit": "Unit cannot change after equipment is configured."})
            if attrs.get("is_active") is False and (tanks.filter(is_active=True).exists() or nozzles.filter(is_active=True).exists()):
                raise serializers.ValidationError({"is_active": "Deactivate linked equipment first."})
        return attrs


class EquipmentSerializer(TenantSerializer):
    def get_fields(self):
        fields = super().get_fields()
        tenant = self.context["request"].tenant
        for name, model in [("product", FuelProduct), ("pump", Pump), ("tank", Tank)]:
            if name in fields:
                fields[name].queryset = model.objects.for_tenant(tenant)
        return fields

    def validate(self, attrs):
        active = attrs.get("is_active", self.instance.is_active if self.instance else True)
        if active:
            for field in ["product", "pump", "tank"]:
                relation = attrs.get(field, getattr(self.instance, field, None))
                if relation and not relation.is_active:
                    raise serializers.ValidationError({field: "Choose active equipment and fuel products."})
        return attrs


class TankSerializer(EquipmentSerializer):
    class Meta:
        model = Tank
        fields = ["id", "name", "product", "capacity", "opening_quantity", "minimum_stock", "is_active", "notes"]
        read_only_fields = ["id"]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            from apps.inventory.models import InventoryMovement
            from apps.shifts.models import NozzleAssignment
            used = InventoryMovement.objects.for_tenant(self.context["request"].tenant).filter(tank=self.instance).exists() or NozzleAssignment.objects.for_tenant(self.context["request"].tenant).filter(tank=self.instance).exists()
            if used and any(key in attrs and attrs[key] != getattr(self.instance, key) for key in ["opening_quantity", "product"]):
                raise serializers.ValidationError({"opening_quantity": "Operational tank history requires stock adjustments instead of setup edits."})
            if "capacity" in attrs:
                from apps.operations.services import stock
                if attrs["capacity"] < stock(self.instance.tenant, self.instance):
                    raise serializers.ValidationError({"capacity": "Capacity cannot be below current stock."})
            linked = Nozzle.objects.for_tenant(self.context["request"].tenant).filter(tank=self.instance)
            if attrs.get("product", self.instance.product) != self.instance.product and linked.exists():
                raise serializers.ValidationError({"product": "Fuel cannot change while nozzles are linked."})
            if attrs.get("is_active") is False and linked.filter(is_active=True).exists():
                raise serializers.ValidationError({"is_active": "Deactivate linked nozzles first."})
        return attrs


class PumpSerializer(TenantSerializer):
    class Meta:
        model = Pump
        fields = ["id", "name", "number", "location", "status", "is_active"]
        read_only_fields = ["id"]
        validators = []

    def validate(self, attrs):
        if self.instance and attrs.get("is_active") is False:
            if Nozzle.objects.for_tenant(self.context["request"].tenant).filter(pump=self.instance, is_active=True).exists():
                raise serializers.ValidationError({"is_active": "Deactivate linked nozzles first."})
        return attrs


class NozzleSerializer(EquipmentSerializer):
    class Meta:
        model = Nozzle
        fields = ["id", "number", "pump", "product", "tank", "opening_meter", "is_active", "notes"]
        read_only_fields = ["id"]
        validators = []

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance:
            from apps.shifts.models import NozzleAssignment
            if NozzleAssignment.objects.for_tenant(self.context["request"].tenant).filter(nozzle=self.instance).exists() and any(key in attrs and attrs[key] != getattr(self.instance, key) for key in ["pump", "product", "tank"]):
                raise serializers.ValidationError({"nozzle": "Equipment relationships cannot change after operational use."})
            if attrs.get("is_active") is False and NozzleAssignment.objects.for_tenant(self.context["request"].tenant).filter(nozzle=self.instance, is_active=True).exists():
                raise serializers.ValidationError({"is_active": "Close the assigned shift before deactivating this nozzle."})
        if self.instance and attrs.get("opening_meter", self.instance.opening_meter) != self.instance.opening_meter:
            raise serializers.ValidationError({"opening_meter": "Opening meter is immutable. Meter corrections belong to the operations module."})
        tank = attrs.get("tank", self.instance.tank if self.instance else None)
        product = attrs.get("product", self.instance.product if self.instance else None)
        if tank and product and tank.product_id != product.pk:
            raise serializers.ValidationError({"tank": "Tank and nozzle must use the same fuel."})
        return attrs


class FuelPriceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelPriceHistory
        fields = ["id", "product", "purchase_price", "selling_price", "reason", "created_at", "created_by"]
