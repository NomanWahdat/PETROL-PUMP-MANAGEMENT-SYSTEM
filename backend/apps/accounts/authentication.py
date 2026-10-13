from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from apps.common.errors import CodedError


class SecureSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        try:
            super().enforce_csrf(request)
        except PermissionDenied as exc:
            raise CodedError("csrf_failed", "Please refresh the page and try again.", 403) from exc
