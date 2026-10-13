import logging

from django.db import connection, DatabaseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "service": "petrol-station-api", "version": "0.1.0"})


class ReadinessView(HealthView):
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DatabaseError:
            logger.exception("Database readiness check failed")
            return Response({"status": "unavailable"}, status=503)
        return Response({"status": "ready"})
