from django.db import migrations
from apps.common.tenant_constraints import add_constraints, remove_constraints

LINKS = [("employee_membership_tenant", "employees_employee", ["tenant_id", "membership_id"], "tenants_membership", ["tenant_id", "id"])]


def forwards(apps, schema_editor):
    add_constraints(schema_editor, LINKS)
    Employee = apps.get_model("employees", "Employee")
    Membership = apps.get_model("tenants", "Membership")
    for membership in Membership.all_tenants.select_related("user"):
        Employee.all_tenants.get_or_create(tenant_id=membership.tenant_id, membership_id=membership.pk,
            defaults={"name": membership.user.first_name or membership.user.username})


def backwards(apps, schema_editor):
    remove_constraints(schema_editor, LINKS)


class Migration(migrations.Migration):
    dependencies = [("employees", "0001_initial"), ("tenants", "0002_rolepolicy_membership_membership_tenant_id_and_more")]
    operations = [migrations.RunPython(forwards, backwards)]
