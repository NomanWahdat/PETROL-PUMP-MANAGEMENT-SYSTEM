from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from apps.stations.models import Station
from apps.employees.models import Employee
from apps.tenants.models import Membership, Tenant


class Command(BaseCommand):
    help = "Create a tenant, station and initial owner atomically. Password is prompted, never accepted as an argument."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--language", choices=["fa", "ps", "en"], default="fa")

    def handle(self, *args, **options):
        User = get_user_model()
        tenant = Tenant(name=options["name"], slug=options["slug"])
        owner = User(username=options["username"], preferred_language=options["language"])
        try:
            tenant.full_clean()
            owner.full_clean(exclude=["password"])
            password = getpass("Owner password: ")
            if password != getpass("Confirm password: "):
                raise CommandError("Passwords do not match.")
            validate_password(password, owner)
            with transaction.atomic():
                tenant.save()
                owner.set_password(password)
                owner.save()
                membership = Membership(tenant=tenant, user=owner, role=Membership.Role.OWNER, created_by=owner)
                membership.full_clean()
                membership.save()
                Employee.all_tenants.create(tenant=tenant, membership=membership, name=owner.username, created_by=owner)
                station = Station(tenant=tenant, name=tenant.name, language=options["language"], created_by=owner)
                station.full_clean()
                station.save()
        except (ValidationError, IntegrityError) as exc:
            raise CommandError("Unable to provision station. Check fields and use a unique slug and username.") from exc
        self.stdout.write(self.style.SUCCESS(f"Station '{tenant.name}' created for owner '{owner.username}'."))
