from apps.common.api import TenantViewSet
from .serializers import EmployeeSerializer


class EmployeeViewSet(TenantViewSet):
    serializer_class = EmployeeSerializer
    read_permission = write_permission = "employees.manage"
    search_fields = ["name", "phone", "membership__user__username"]

    def get_queryset(self):
        # Employee activity lives on the membership, not a duplicate flag.
        queryset = EmployeeSerializer.Meta.model.objects.for_tenant(self.request.tenant).select_related("membership__user").order_by("name")
        active = self.request.query_params.get("is_active")
        if active in {"true", "false"}:
            queryset = queryset.filter(membership__is_active=active == "true")
        return queryset
