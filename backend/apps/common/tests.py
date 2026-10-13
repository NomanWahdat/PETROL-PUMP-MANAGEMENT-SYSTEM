from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase


class HealthTests(TestCase):
    def test_liveness_is_public_and_does_not_query_database(self):
        with self.assertNumQueries(0):
            response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_readiness_checks_database(self):
        response = self.client.get("/api/v1/ready/")
        self.assertEqual(response.status_code, 200)

    def test_readiness_failure_does_not_expose_database_details(self):
        with patch("apps.common.views.connection.cursor", side_effect=DatabaseError("private-host password")):
            with self.assertLogs("apps.common.views", level="ERROR"):
                response = self.client.get("/api/v1/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private-host", response.content.decode())
