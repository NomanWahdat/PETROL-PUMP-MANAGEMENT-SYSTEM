from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework import serializers

from apps.common.api import validated_save
from apps.employees.models import Employee
from apps.stations.models import Station
from .models import Tenant, Membership, RolePolicy
from .permissions import KNOWN_PERMISSIONS

User = get_user_model()


class TenantSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(write_only=True, required=False, max_length=150)
    owner_password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=256)
    owner_name = serializers.CharField(write_only=True, required=False, max_length=150)
    language = serializers.ChoiceField(choices=["fa", "ps", "en"], write_only=True, required=False, default="fa")
    owner_username_display = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "is_active", "primary_color", "secondary_color", "owner_username", "owner_password", "owner_name", "owner_username_display", "language", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_owner_username_display(self, instance):
        owner = Membership.objects.for_tenant(instance).filter(role="owner", is_active=True).select_related("user").first()
        return owner.user.username if owner else ""

    def validate(self, attrs):
        if self.instance and any(key in attrs for key in ["owner_username", "owner_password", "owner_name", "language"]):
            raise serializers.ValidationError({"owner_username": "Owner creation fields cannot be used when editing a tenant."})
        if not self.instance:
            if not attrs.get("owner_username") or not attrs.get("owner_password") or not attrs.get("owner_name"):
                raise serializers.ValidationError({"owner_username": "Initial owner name, username and password are required."})
            owner = User(username=attrs["owner_username"])
            try:
                owner.full_clean(exclude=["password"])
                validate_password(attrs["owner_password"], owner)
            except ModelValidationError as exc:
                raise serializers.ValidationError({"owner_username": "Use an available username and a strong password."}) from exc
        return attrs

    def create(self, validated_data):
        username = validated_data.pop("owner_username")
        password = validated_data.pop("owner_password")
        name = validated_data.pop("owner_name")
        language = validated_data.pop("language", "fa")
        tenant = Tenant(**validated_data)
        validated_save(tenant)
        owner = User.objects.create_user(username=username, password=password, preferred_language=language)
        actor = self.context["request"].user
        membership = Membership.all_tenants.create(tenant=tenant, user=owner, role="owner", created_by=actor)
        Employee.all_tenants.create(tenant=tenant, membership=membership, name=name, created_by=actor)
        Station.all_tenants.create(tenant=tenant, name=tenant.name, owner_name=name, language=language, created_by=actor)
        return tenant

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        validated_save(instance)
        if "name" in validated_data:
            Station.objects.for_tenant(instance).update(name=instance.name)
        return instance


class RolePolicySerializer(serializers.ModelSerializer):
    permissions = serializers.ListField(child=serializers.ChoiceField(choices=sorted(KNOWN_PERMISSIONS)))

    class Meta:
        model = RolePolicy
        fields = ["role", "permissions"]
        validators = []

    def validate(self, attrs):
        if attrs["role"] == "owner" and not {"station.view", "access.manage"}.issubset(attrs["permissions"]):
            raise serializers.ValidationError({"permissions": "Owner requires station view and access management."})
        attrs["permissions"] = sorted(set(attrs["permissions"]))
        return attrs


class PlatformUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=256)
    tenant_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    role = serializers.ChoiceField(choices=Membership.Role.choices, write_only=True, required=False)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email", "is_active", "is_superuser", "preferred_language", "password", "tenant_id", "role"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if self.instance:
            if any(k in attrs for k in ["username", "password", "tenant_id", "role"]):
                raise serializers.ValidationError({"username": "Existing identities and passwords are managed by the account holder."})
            if self.instance.pk == self.context["request"].user.pk and (attrs.get("is_active") is False or attrs.get("is_superuser") is False):
                raise serializers.ValidationError({"is_active": "You cannot revoke your own system access."})
            if self.instance.is_superuser and (attrs.get("is_active") is False or attrs.get("is_superuser") is False):
                if not User.objects.filter(is_active=True, is_superuser=True).exclude(pk=self.instance.pk).exists():
                    raise serializers.ValidationError({"is_superuser": "At least one active system administrator is required."})
            if attrs.get("is_active") is False:
                owners = Membership.all_tenants.filter(user=self.instance, role="owner", is_active=True, tenant__is_active=True)
                for membership in owners:
                    if not Membership.objects.for_tenant(membership.tenant).filter(role="owner", is_active=True, user__is_active=True).exclude(user=self.instance).exists():
                        raise serializers.ValidationError({"is_active": "Assign another active owner before disabling this account."})
        else:
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "A password is required."})
            if not attrs.get("is_superuser") and not attrs.get("tenant_id"):
                raise serializers.ValidationError({"tenant_id": "Assign a station for a non-system user."})
        if attrs.get("tenant_id"):
            if not Tenant.objects.filter(pk=attrs["tenant_id"], is_active=True).exists():
                raise serializers.ValidationError({"tenant_id": "Choose an active station."})
            if not attrs.get("role"):
                raise serializers.ValidationError({"role": "Choose a station role."})
        if attrs.get("password"):
            try:
                validate_password(attrs["password"], User(username=attrs.get("username", "")))
            except ModelValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    def create(self, validated_data):
        tenant_id = validated_data.pop("tenant_id", None)
        role = validated_data.pop("role", None)
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.is_staff = user.is_superuser
        user.set_password(password)
        validated_save(user)
        if tenant_id:
            actor = self.context["request"].user
            membership = Membership.all_tenants.create(tenant_id=tenant_id, user=user, role=role, created_by=actor)
            Employee.all_tenants.create(tenant_id=tenant_id, membership=membership, name=user.get_full_name() or user.username, created_by=actor)
        return user

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.is_staff = instance.is_superuser
        validated_save(instance)
        return instance
