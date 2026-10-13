from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.common.views import HealthView, ReadinessView
from apps.stations.views import StationView, ComplianceViewSet
from apps.stations.logo import LogoView, PlatformLogoView, PublicBrandingView, PublicLogoView
from apps.tenants.views import TenantViewSet, PlatformUserViewSet, PlatformStatusView, PlatformAuditViewSet, RolePolicyView
from apps.employees.views import EmployeeViewSet
from apps.fuel.views import FuelProductViewSet, FuelPriceHistoryViewSet, TankViewSet, PumpViewSet, NozzleViewSet
from apps.operations.views import (SupplierViewSet, CustomerViewSet, ShiftViewSet, SaleViewSet, PurchaseViewSet, PaymentViewSet, MeterViewSet, InventoryViewSet, PhysicalViewSet, CashViewSet, DayViewSet, OperationsOptionsView)

router = DefaultRouter()
for prefix, view, basename in [
    ("platform/tenants", TenantViewSet, "platform-tenant"),
    ("platform/users", PlatformUserViewSet, "platform-user"),
    ("platform/audit", PlatformAuditViewSet, "platform-audit"),
    ("employees", EmployeeViewSet, "employee"),
    ("fuel/products", FuelProductViewSet, "fuel-product"),
    ("fuel/price-history", FuelPriceHistoryViewSet, "fuel-price"),
    ("tanks", TankViewSet, "tank"), ("pumps", PumpViewSet, "pump"), ("nozzles", NozzleViewSet, "nozzle"),
    ("station/compliance", ComplianceViewSet, "compliance"),
    ("suppliers", SupplierViewSet, "supplier"), ("customers", CustomerViewSet, "customer"),
    ("shifts", ShiftViewSet, "shift"), ("sales", SaleViewSet, "sale"),
    ("purchases", PurchaseViewSet, "purchase"), ("customer-payments", PaymentViewSet, "customer-payment"),
    ("meter-readings", MeterViewSet, "meter-reading"), ("inventory-movements", InventoryViewSet, "inventory-movement"),
    ("physical-stock", PhysicalViewSet, "physical-stock"), ("cash-movements", CashViewSet, "cash-movement"),
    ("daily-closings", DayViewSet, "daily-closing"),
]:
    router.register(prefix, view, basename=basename)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/ready/", ReadinessView.as_view(), name="ready"),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/station/", StationView.as_view(), name="station"),
    path("api/v1/station/logo/", LogoView.as_view()),
    path("api/v1/branding/<slug:slug>/", PublicBrandingView.as_view()),
    path("api/v1/branding/<slug:slug>/logo/", PublicLogoView.as_view()),
    path("api/v1/platform/tenants/<uuid:pk>/logo/", PlatformLogoView.as_view()),
    path("api/v1/roles/", RolePolicyView.as_view()),
    path("api/v1/operations/options/", OperationsOptionsView.as_view()),
    path("api/v1/platform/status/", PlatformStatusView.as_view()),
    path("api/v1/", include(router.urls)),
]
