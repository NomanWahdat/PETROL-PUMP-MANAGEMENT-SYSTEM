from django.urls import path

from .views import CsrfView, LoginView, LogoutView, MeView, MembershipsView, SelectTenantView, PasswordView, PlatformContextView

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("memberships/", MembershipsView.as_view()),
    path("select-tenant/", SelectTenantView.as_view()),
    path("platform/", PlatformContextView.as_view()),
    path("password/", PasswordView.as_view()),
]
