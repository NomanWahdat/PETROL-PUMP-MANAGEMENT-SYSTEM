from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.errors import CodedError
from apps.common.api import audit, TenantViewSet
from apps.tenants.models import Tenant
from apps.tenants.permissions import HasTenantPermission, effective_permissions, lock_tenant_access
from .models import Station
from .serializers import StationSerializer, ComplianceSerializer


@method_decorator(never_cache, name="dispatch")
class StationView(APIView):
    permission_classes = [HasTenantPermission]
    def get_required_permission(self, request):
        return "station.view" if request.method in {"GET", "HEAD", "OPTIONS"} else "station.manage"

    def station(self, request):
        station = Station.objects.for_tenant(request.tenant).select_related("tenant").first()
        if station is None:
            raise CodedError("station_missing", "Station setup is incomplete.", 404)
        return station

    def get(self, request):
        data = StationSerializer(self.station(request), context={"request": request}).data
        if "station.manage" not in effective_permissions(request.membership):
            data = {key: data[key] for key in ["id", "slug", "name", "address", "phone", "currency", "language", "timezone", "primary_color", "secondary_color", "logo_url"]}
        return Response(data)

    def patch(self, request):
        with transaction.atomic():
            lock_tenant_access(request, self.get_required_permission(request))
            station = self.station(request)
            before = dict(StationSerializer(station).data)
            serializer = StationSerializer(station, data=request.data, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            serializer.save(updated_by=request.user)
            audit(request, "station_updated", station, {"before": before, "after": dict(serializer.data)})
        return Response(serializer.data)


class ComplianceViewSet(TenantViewSet):
    serializer_class = ComplianceSerializer
    read_permission = write_permission = "station.manage"
    search_fields = ["title", "reference"]

    def get_queryset(self):
        return ComplianceSerializer.Meta.model.objects.for_tenant(self.request.tenant).order_by("-created_at")
