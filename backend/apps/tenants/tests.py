from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.common.models import TenantScopeRequired
from apps.stations.models import ComplianceRecord, Station
from .models import Membership, Tenant


class FoundationModelTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Station", slug="test-station")

    def test_unscoped_tenant_queries_fail_closed(self):
        with self.assertRaises(TenantScopeRequired):
            Station.objects.all()
        with self.assertRaises(TenantScopeRequired):
            Station.objects.for_tenant(None)

    def test_scoped_query_does_not_return_other_tenants(self):
        other = Tenant.objects.create(name="Other", slug="other")
        Station.all_tenants.create(tenant=other, name="Other")
        self.assertEqual(Station.objects.for_tenant(self.tenant).count(), 0)

    def test_database_prevents_duplicate_station(self):
        Station.all_tenants.create(tenant=self.tenant, name="First")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Station.all_tenants.create(tenant=self.tenant, name="Second")

    def test_compliance_dates_are_constrained_in_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ComplianceRecord.all_tenants.create(tenant=self.tenant, title="Record", issue_date="2026-10-12", expiry_date="2026-10-01")

    def test_permission_override_rejects_unknown_permissions(self):
        membership = Membership(permission_overrides={"system.admin": True})
        with self.assertRaises(ValidationError):
            membership.clean()

    def test_provision_command_creates_all_records(self):
        with patch("apps.tenants.management.commands.provision_station.getpass", return_value="A-valid-station-password-941!"):
            call_command("provision_station", name="New Station", slug="new-station", username="new-owner", verbosity=0)
        tenant = Tenant.objects.get(slug="new-station")
        owner = get_user_model().objects.get(username="new-owner")
        self.assertTrue(owner.check_password("A-valid-station-password-941!"))
        self.assertFalse(owner.is_superuser)
        self.assertEqual(Station.objects.for_tenant(tenant).count(), 1)
        self.assertEqual(Membership.objects.for_tenant(tenant).get().role, "owner")

    def test_weak_provisioning_password_creates_no_partial_records(self):
        with patch("apps.tenants.management.commands.provision_station.getpass", return_value="123"):
            with self.assertRaises(CommandError):
                call_command("provision_station", name="New Station", slug="new-station", username="new-owner")
        self.assertFalse(Tenant.objects.filter(slug="new-station").exists())
        self.assertFalse(get_user_model().objects.filter(username="new-owner").exists())
