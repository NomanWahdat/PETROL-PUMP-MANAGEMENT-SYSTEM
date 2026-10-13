"""Explicit development accounts; never invoked by migrations or startup."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.audit.models import PlatformAuditLog
from apps.employees.models import Employee
from apps.stations.models import Station
from apps.tenants.models import Tenant, Membership

DEVELOPMENT_PASSWORD = "PetrolDemo2026!"
DEMO_SLUG = "development-demo"
DEMO_ROLES = ("owner", "manager", "worker", "accountant")


class Command(BaseCommand):
    help = "Create a separate development station and five demo logins. Requires DEBUG; never resets existing users."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo accounts are disabled when DJANGO_DEBUG=false.")
        User = get_user_model()
        usernames = ["demo-"+role for role in DEMO_ROLES] + ["demo-superadmin"]
        with transaction.atomic():
            if Tenant.objects.filter(slug=DEMO_SLUG).exists() or User.objects.filter(username__in=usernames).exists():
                raise CommandError("Demo records already exist or usernames are occupied. No existing records/passwords were changed.")
            admin = User.objects.create_superuser(username="demo-superadmin", password=DEVELOPMENT_PASSWORD, preferred_language="en")
            tenant = Tenant.objects.create(name="Development Demo Station", slug=DEMO_SLUG)
            Station.all_tenants.create(tenant=tenant, name=tenant.name, language="en", created_by=admin)
            for role in DEMO_ROLES:
                user = User.objects.create_user(username="demo-"+role, password=DEVELOPMENT_PASSWORD, preferred_language="en")
                member = Membership.all_tenants.create(tenant=tenant, user=user, role=role, created_by=admin)
                Employee.all_tenants.create(tenant=tenant, membership=member, name="Demo "+role.title(), created_by=admin)
            PlatformAuditLog.objects.create(actor=admin, action="development_accounts_created", object_id=str(tenant.pk))
        self.stdout.write(self.style.SUCCESS("Development Demo Station created; existing stations were preserved. No sample fuel transactions were added."))
        self.stdout.write("Usernames: "+", ".join(usernames))
        self.stdout.write("Development-only initial password: "+DEVELOPMENT_PASSWORD)
