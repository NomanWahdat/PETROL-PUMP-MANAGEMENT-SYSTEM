from django.db import migrations
from apps.common.tenant_constraints import add_constraints, remove_constraints

LINKS = [
    ("tank_product_tenant", "fuel_tank", ["tenant_id", "product_id"], "fuel_fuelproduct", ["tenant_id", "id"]),
    ("history_product_tenant", "fuel_fuelpricehistory", ["tenant_id", "product_id"], "fuel_fuelproduct", ["tenant_id", "id"]),
    ("nozzle_pump_tenant", "fuel_nozzle", ["tenant_id", "pump_id"], "fuel_pump", ["tenant_id", "id"]),
    ("nozzle_product_tenant", "fuel_nozzle", ["tenant_id", "product_id"], "fuel_fuelproduct", ["tenant_id", "id"]),
    ("nozzle_tank_product_tenant", "fuel_nozzle", ["tenant_id", "tank_id", "product_id"], "fuel_tank", ["tenant_id", "id", "product_id"]),
]


def forwards(apps, schema_editor):
    add_constraints(schema_editor, LINKS)


def backwards(apps, schema_editor):
    remove_constraints(schema_editor, LINKS)


class Migration(migrations.Migration):
    dependencies = [("fuel", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
