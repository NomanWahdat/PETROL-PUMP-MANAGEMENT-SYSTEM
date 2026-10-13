"""Disposable browser fixtures. Refuses to run against a non-test database."""
import json
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse

url = urlparse(os.environ.get("DATABASE_URL", ""))
if url.hostname != "127.0.0.1" or url.port != 55432 or url.path != "/petrol_station_test_base":
    raise SystemExit("Browser fixtures require the isolated loopback test database on port 55432.")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.tenants.models import Tenant, Membership
from apps.stations.models import Station
from apps.employees.models import Employee

suffix = secrets.token_hex(5)
password = secrets.token_urlsafe(24)
users = {}
with transaction.atomic():
    tenant = Tenant.objects.create(name="Browser QA Station", slug="browser-qa-" + suffix)
    Station.all_tenants.create(tenant=tenant, name=tenant.name, language="fa")
    for role in ["owner", "worker", "accountant"]:
        user = get_user_model().objects.create_user(username="qa-" + role + "-" + suffix, password=password)
        membership = Membership.all_tenants.create(tenant=tenant, user=user, role=role)
        Employee.all_tenants.create(tenant=tenant, membership=membership, name="QA " + role)
        users[role] = {"username": user.username, "password": password}
    admin = get_user_model().objects.create_superuser(username="qa-platform-" + suffix, password=password)
    users["platform"] = {"username": admin.username, "password": password}
if os.environ.get("BROWSER_FUEL_OPERATIONS") == "true":
    from apps.fuel.models import FuelProduct, Tank, Pump, Nozzle
    from apps.suppliers.models import Supplier
    from apps.customers.models import Customer
    with transaction.atomic():
        product = FuelProduct.all_tenants.create(tenant=tenant, name="Diesel", code="fixture-diesel", selling_price="70.0000")
        tank = Tank.all_tenants.create(tenant=tenant, name="Tank 1", product=product, capacity="1000.000", opening_quantity="500.000")
        pump = Pump.all_tenants.create(tenant=tenant, name="Pump 1", number="1")
        Nozzle.all_tenants.create(tenant=tenant, number="1", pump=pump, tank=tank, product=product, opening_meter="100.000")
print(json.dumps({"users": users, "suffix": suffix, "password": password, "tenant_id": str(tenant.pk)}))
