from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction
from rest_framework import serializers

from apps.common.api import TenantSerializer, validated_save
from apps.tenants.models import Membership
from apps.tenants.permissions import KNOWN_PERMISSIONS, effective_permissions
from .models import Employee

User = get_user_model()


class EmployeeSerializer(TenantSerializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=256)
    role = serializers.ChoiceField(choices=Membership.Role.choices)
    is_active = serializers.BooleanField(required=False, default=True)
    permission_overrides = serializers.JSONField(required=False, default=dict)

    class Meta:
        model = Employee
        fields = ["id", "name", "phone", "address", "job_title", "joined_on", "notes", "username", "password", "role", "is_active", "permission_overrides"]
        read_only_fields = ["id"]
        validators = []

    def to_representation(self, instance):
        values = dict(username=instance.membership.user.username, role=instance.membership.role,
                      is_active=instance.membership.is_active, permission_overrides=instance.membership.permission_overrides)
        return {name: field.to_representation(values[name] if name in values else getattr(instance, name))
                if (values[name] if name in values else getattr(instance, name)) is not None else None
                for name, field in self.fields.items() if not field.write_only}

    def validate(self, attrs):
        request = self.context["request"]
        actor = request.membership
        target = self.instance.membership if self.instance else None
        role = attrs.get("role", target.role if target else "worker")
        access = "access.manage" in effective_permissions(actor)
        if not access and (role != "worker" or (target and target.role != "worker") or
            ("permission_overrides" in attrs and attrs["permission_overrides"] != (target.permission_overrides if target else {}))):
            raise serializers.ValidationError({"role": "Only workers can be managed with operational employee permission."})
        if (role == "owner" or (target and target.role == "owner")) and actor.role != "owner":
            raise serializers.ValidationError({"role": "Owner access can only be managed by an owner."})
        overrides = attrs.get("permission_overrides", target.permission_overrides if target else {})
        if not isinstance(overrides, dict) or any(key not in KNOWN_PERMISSIONS or type(value) is not bool for key, value in overrides.items()):
            raise serializers.ValidationError({"permission_overrides": "Use known permissions and boolean values."})
        if role == "owner" and overrides.get("access.manage") is False:
            raise serializers.ValidationError({"permission_overrides": "Owner access management cannot be removed."})
        if target and target.user_id == request.user.pk and (role != target.role or attrs.get("is_active") is False or overrides != target.permission_overrides):
            raise serializers.ValidationError({"role": "You cannot change your own access here."})
        if target and target.role == "owner" and (role != "owner" or attrs.get("is_active") is False):
            if not Membership.objects.for_tenant(request.tenant).filter(role="owner", is_active=True, user__is_active=True).exclude(pk=target.pk).exists():
                raise serializers.ValidationError({"role": "At least one active owner is required."})
        username = attrs.get("username", target.user.username if target else "")
        if target and username != target.user.username:
            raise serializers.ValidationError({"username": "Usernames cannot be changed through employee management."})
        if not target:
            candidate = User(username=username)
            try:
                candidate.full_clean(exclude=["password"])
            except ModelValidationError as exc:
                raise serializers.ValidationError({"username": "Use a valid, available username."}) from exc
            if not attrs.get("password"):
                raise serializers.ValidationError({"password": "A password is required for a new employee."})
        if attrs.get("password"):
            if target and (not access or target.user.is_superuser or Membership.all_tenants.filter(user=target.user).count() != 1):
                raise serializers.ValidationError({"password": "This account's password must be changed by the account holder."})
            try:
                validate_password(attrs["password"], target.user if target else User(username=username))
            except ModelValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        role = validated_data.pop("role")
        active = validated_data.pop("is_active", True)
        overrides = validated_data.pop("permission_overrides", {})
        user = User.objects.create_user(username=username, password=password, preferred_language=self.context["request"].user.preferred_language)
        membership = Membership(tenant=validated_data["tenant"], user=user, role=role, is_active=active,
                                permission_overrides=overrides, created_by=validated_data["created_by"])
        validated_save(membership)
        return super().create({**validated_data, "membership": membership})

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop("username", None)
        password = validated_data.pop("password", None)
        membership = instance.membership
        for key in ["role", "is_active", "permission_overrides"]:
            if key in validated_data:
                setattr(membership, key, validated_data.pop(key))
        membership.updated_by = validated_data["updated_by"]
        validated_save(membership)
        if password:
            membership.user.set_password(password)
            membership.user.save(update_fields=["password"])
        return super().update(instance, validated_data)
