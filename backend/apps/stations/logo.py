from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404

from apps.common.api import audit
from apps.common.errors import CodedError
from apps.tenants.models import Tenant
from apps.tenants.permissions import HasTenantPermission, IsPlatformAdmin, lock_tenant_access
from apps.audit.models import PlatformAuditLog
from .models import StationLogo


@method_decorator(never_cache, name="dispatch")
class LogoView(APIView):
    permission_classes = [HasTenantPermission]
    parser_classes = [MultiPartParser]

    def get_required_permission(self, request):
        return "station.view" if request.method in {"GET", "HEAD", "OPTIONS"} else "station.manage"

    def tenant(self, request):
        return request.tenant

    def lock(self, request):
        return lock_tenant_access(request, self.get_required_permission(request))

    def record_change(self, request, tenant):
        audit(request, "logo_changed", tenant)

    def get(self, request, **kwargs):
        tenant = self.tenant(request)
        path = tenant.logo_path
        if not path or not path.startswith(f"logos/{tenant.pk}/") or ".." in PurePosixPath(path).parts:
            raise CodedError("not_found", "Logo is unavailable.", 404)
        stored = StationLogo.objects.for_tenant(tenant).filter(path=path).first()
        if stored is not None:
            response = HttpResponse(bytes(stored.image), content_type="image/png")
        else:
            try:
                response = FileResponse(default_storage.open(path, "rb"), content_type="image/png")
            except FileNotFoundError:
                raise CodedError("not_found", "Logo is unavailable.", 404)
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Disposition"] = 'inline; filename="station-logo.png"'
        return response

    def post(self, request, **kwargs):
        target = self.tenant(request)
        upload = request.FILES.get("logo")
        if upload is None or upload.size > 2 * 1024 * 1024:
            raise serializers.ValidationError({"logo": "Choose an image up to 2 MB."})
        try:
            with Image.open(upload) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"} or image.width > 2048 or image.height > 2048:
                    raise ValueError("Invalid image format or dimensions")
                image.load()
                clean = Image.new("RGBA", image.size)
                clean.paste(image.convert("RGBA"))
                output = BytesIO()
                clean.save(output, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise serializers.ValidationError({"logo": "Use a valid PNG, JPEG or WebP image up to 2048 pixels on each side."}) from exc
        png = output.getvalue()
        if settings.LOGO_STORAGE == "database" and len(png) > 2 * 1024 * 1024:
            raise serializers.ValidationError({"logo": "The decoded PNG exceeds 2 MB. Choose a smaller image."})
        saved = f"logos/{target.pk}/{uuid4()}.png"
        file_saved = settings.LOGO_STORAGE == "file"
        if file_saved:
            saved = default_storage.save(saved, ContentFile(png))
        try:
            with transaction.atomic():
                tenant = self.lock(request)
                if not file_saved:
                    values = {"path": saved, "image": png, "updated_by": request.user}
                    StationLogo.all_tenants.update_or_create(tenant=tenant, defaults=values, create_defaults={**values, "created_by": request.user})
                else:
                    StationLogo.objects.for_tenant(tenant).delete()
                previous = tenant.logo_path
                tenant.logo_path = saved
                tenant.save(update_fields=["logo_path", "updated_at"])
                self.record_change(request, tenant)
                if previous:
                    transaction.on_commit(lambda: default_storage.delete(previous))
        except Exception:
            if file_saved:
                default_storage.delete(saved)
            raise
        return Response({"logo_url": f"/api/v1/branding/{tenant.slug}/logo/?v={tenant.updated_at.timestamp()}"})


class PlatformLogoView(LogoView):
    permission_classes = [IsPlatformAdmin]

    def tenant(self, request):
        return get_object_or_404(Tenant, pk=self.kwargs["pk"])

    def lock(self, request):
        tenant = get_object_or_404(Tenant.objects.select_for_update(), pk=self.kwargs["pk"])
        if not get_user_model().objects.filter(pk=request.user.pk, is_active=True, is_superuser=True).exists():
            raise CodedError("permission_denied", "Access denied.", 403)
        return tenant

    def record_change(self, request, tenant):
        PlatformAuditLog.objects.create(actor=request.user, action="logo_changed", object_id=str(tenant.pk))


class PublicLogoView(LogoView):
    # Only the brand image is public. No membership or financial data is exposed.
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def tenant(self, request):
        return get_object_or_404(Tenant, slug=self.kwargs["slug"], is_active=True)


@method_decorator(never_cache, name="dispatch")
class PublicBrandingView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, slug):
        tenant = get_object_or_404(Tenant, slug=slug, is_active=True)
        return Response({"name": tenant.name, "slug": tenant.slug, "primary_color": tenant.primary_color,
            "logo_url": f"/api/v1/branding/{tenant.slug}/logo/?v={tenant.updated_at.timestamp()}" if tenant.logo_path else ""})
