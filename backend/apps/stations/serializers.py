import re
from rest_framework import serializers
from apps.common.api import TenantSerializer
from apps.common.serializers import ExactDecimal
from .models import Station, ComplianceRecord


class StationSerializer(TenantSerializer):
    slug = serializers.CharField(source="tenant.slug", read_only=True)
    primary_color = serializers.RegexField(r"^#[0-9a-fA-F]{6}$", source="tenant.primary_color", max_length=7, required=False)
    secondary_color = serializers.RegexField(r"^#[0-9a-fA-F]{6}$", source="tenant.secondary_color", max_length=7, required=False)
    logo_url = serializers.SerializerMethodField()

    class Meta:
        model = Station
        fields = ["id", "slug", "name", "address", "province", "district", "phone", "email", "owner_name", "currency", "language", "timezone", "date_format", "receipt_header", "receipt_footer", "settings", "primary_color", "secondary_color", "logo_url"]
        read_only_fields = ["id"]
        validators = []

    def get_logo_url(self, instance):
        return f"/api/v1/station/logo/?v={instance.tenant.updated_at.timestamp()}" if instance.tenant.logo_path else ""

    def validate_date_format(self, value):
        if value not in {"yyyy-MM-dd", "dd/MM/yyyy", "MM/dd/yyyy"}:
            raise serializers.ValidationError("Choose a supported date format.")
        return value

    def validate_settings(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Settings must be an object.")
        allowed = {"payment_methods", "expense_categories", "tax_enabled", "tax_rate", "cash_difference_threshold", "stock_variance_threshold", "opening_time", "closing_time", "receipt_width"}
        if set(value) - allowed:
            raise serializers.ValidationError("Unknown setting.")
        for key in ["payment_methods", "expense_categories"]:
            if key in value and (not isinstance(value[key], list) or len(value[key]) > 50 or any(not isinstance(v, str) or not v.strip() or len(v) > 80 for v in value[key])):
                raise serializers.ValidationError("Use up to 50 non-empty labels for each list.")
        if "tax_enabled" in value and type(value["tax_enabled"]) is not bool:
            raise serializers.ValidationError("Tax enabled must be true or false.")
        for key in ["tax_rate", "cash_difference_threshold", "stock_variance_threshold"]:
            if key in value:
                decimal = ExactDecimal(max_digits=18, decimal_places=4, min_value=0, max_value=100 if key == "tax_rate" else None).run_validation(value[key])
                value[key] = str(decimal)
        for key in ["opening_time", "closing_time"]:
            if key in value and (not isinstance(value[key], str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value[key])):
                raise serializers.ValidationError("Use HH:mm for station times.")
        if "receipt_width" in value and value["receipt_width"] not in {"58", "80"}:
            raise serializers.ValidationError("Receipt width must be 58 or 80 mm.")
        return value

    def update(self, instance, validated_data):
        from apps.cash.models import DailyClosing
        if DailyClosing.objects.for_tenant(instance.tenant).exists() and any(key in validated_data and validated_data[key] != getattr(instance, key) for key in ["currency", "timezone"]):
            raise serializers.ValidationError({"currency": "Currency and timezone cannot change after operational posting."})
        tenant = instance.tenant
        branding = validated_data.pop("tenant", {})
        for key in ["primary_color", "secondary_color"]:
            if key in branding:
                setattr(tenant, key, branding[key])
        tenant.name = validated_data.get("name", instance.name)
        tenant.save(update_fields=["name", "primary_color", "secondary_color", "updated_at"])
        if "settings" in validated_data:
            validated_data["settings"] = {**instance.settings, **validated_data["settings"]}
        return super().update(instance, validated_data)


class ComplianceSerializer(TenantSerializer):
    class Meta:
        model = ComplianceRecord
        fields = ["id", "title", "authority", "reference", "source_url", "issue_date", "expiry_date", "status", "notes"]
        read_only_fields = ["id"]
        validators = []
