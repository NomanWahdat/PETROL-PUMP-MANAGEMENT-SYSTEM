"""Private, portable data transfer. Never used by HTTP endpoints or startup."""
import hashlib
import json
from collections import Counter
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED

from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.utils import timezone
from PIL import Image

from apps.tenants.models import Tenant
from apps.stations.models import StationLogo


def transfer_models():
    models = [model for model in apps.get_models() if model._meta.app_config.name.startswith("apps.") and model is not StationLogo]
    return [apps.get_model("auth", "Group"), *models]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def valid_logo_path(path, tenant_id):
    return path.startswith(f"logos/{tenant_id}/") and ".." not in PurePosixPath(path).parts and not PurePosixPath(path).is_absolute() and "\\" not in path


def export_bundle(output):
    output = Path(output).resolve()
    if output.exists():
        raise CommandError("The output already exists. Choose a new filename; no existing export was overwritten.")
    output.parent.mkdir(parents=True, exist_ok=True)
    already_atomic = connection.in_atomic_block
    with transaction.atomic():
        if connection.vendor == "postgresql" and not already_atomic:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        records, counts = [], {}
        for model in transfer_models():
            rows = list(model._base_manager.order_by("pk"))
            counts[model._meta.label_lower] = len(rows)
            records.extend(rows)
        data = serializers.serialize("json", records, use_natural_foreign_keys=True).encode("utf-8")
        images = {}
        for tenant in Tenant.objects.exclude(logo_path="").order_by("pk"):
            if not valid_logo_path(tenant.logo_path, tenant.pk):
                raise CommandError("A logo storage path is invalid. Export refused.")
            stored = StationLogo.objects.for_tenant(tenant).filter(path=tenant.logo_path).first()
            if stored:
                png = bytes(stored.image)
            else:
                try:
                    with default_storage.open(tenant.logo_path, "rb") as handle:
                        png = handle.read(2 * 1024 * 1024 + 1)
                except FileNotFoundError as exc:
                    raise CommandError("A station logo is missing. Repair it before exporting.") from exc
            validate_png(png)
            images[tenant.logo_path] = png
        manifest = {"version": 1, "exported_at": timezone.now().isoformat(), "source_vendor": connection.vendor,
            "counts": counts, "data_sha256": digest(data), "logos": {path: digest(png) for path, png in images.items()}}
        with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
            archive.writestr("data.json", data)
            for path, png in images.items():
                archive.writestr(path, png)
    # Includes password hashes and private business data. Store/share privately.
    output.chmod(0o600)
    return manifest


def validate_png(png):
    if not png or len(png) > 2 * 1024 * 1024:
        raise CommandError("A logo exceeds the 2 MB transfer limit.")
    try:
        with Image.open(BytesIO(png)) as image:
            if image.format != "PNG" or max(image.size) > 2048:
                raise ValueError("Invalid PNG")
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise CommandError("A logo is not a valid sanitized PNG.") from exc


def read_bundle(source):
    try:
        with ZipFile(source) as archive:
            names = archive.namelist()
            if len(set(names)) != len(names) or sum(info.file_size for info in archive.infolist()) > 128 * 1024 * 1024:
                raise CommandError("Invalid or oversized transfer bundle.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("version") != 1 or not isinstance(manifest.get("logos"), dict):
                raise CommandError("Unsupported transfer bundle.")
            if set(names) != {"manifest.json", "data.json", *manifest["logos"]}:
                raise CommandError("Unexpected files in transfer bundle.")
            data = archive.read("data.json")
            if digest(data) != manifest.get("data_sha256"):
                raise CommandError("Transfer data checksum failed.")
            allowed = {model._meta.label_lower for model in transfer_models()}
            records = json.loads(data)
            if not isinstance(records, list) or any(row.get("model") not in allowed for row in records):
                raise CommandError("Unexpected records in transfer bundle.")
            expected = {key: value for key, value in manifest.get("counts", {}).items() if value}
            if dict(Counter(row["model"] for row in records)) != expected:
                raise CommandError("Transfer record counts do not match.")
            tenants = {str(row["pk"]): row["fields"].get("logo_path", "") for row in records if row["model"] == "tenants.tenant"}
            if set(manifest["logos"]) != {path for path in tenants.values() if path}:
                raise CommandError("Transfer logo references do not match.")
            images = {}
            for tenant_id, path in tenants.items():
                if not path:
                    continue
                if not valid_logo_path(path, tenant_id):
                    raise CommandError("Unsafe logo path in transfer bundle.")
                png = archive.read(path)
                if digest(png) != manifest["logos"][path]:
                    raise CommandError("Logo checksum failed.")
                validate_png(png)
                images[path] = png
            return manifest, data, records, images
    except CommandError:
        raise
    except Exception as exc:
        raise CommandError("Unable to read the private transfer bundle.") from exc


def import_bundle(source, passwords):
    """Load one fresh PostgreSQL database; never merge, flush or overwrite records."""
    if connection.vendor != "postgresql":
        raise CommandError("The transfer target must be a fresh PostgreSQL database.")
    manifest, data, records, images = read_bundle(source)
    source_admins = {row["fields"]["username"] for row in records if row["model"] == "accounts.user" and row["fields"]["is_superuser"]}
    if set(passwords) != source_admins:
        raise CommandError("A new private password is required for every imported Super Admin.")
    saved_files = []
    try:
        with transaction.atomic():
            # Also serialize concurrent import attempts into this empty target.
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(764129031)")
            if any(model._base_manager.exists() for model in transfer_models()) or StationLogo.all_tenants.exists():
                raise CommandError("Target database already contains application data. Nothing was overwritten.")
            # Deserialize in memory; no private fixture is written to the server disk.
            deferred = []
            for item in serializers.deserialize("json", data.decode("utf-8"), handle_forward_references=True):
                item.save()
                if item.deferred_fields:
                    deferred.append(item)
            for item in deferred:
                item.save_deferred_fields()
            from django.contrib.auth import get_user_model
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            for username, password in passwords.items():
                user = get_user_model().objects.get(username=username, is_superuser=True)
                try:
                    validate_password(password, user)
                    if password == "PetrolDemo2026!":
                        raise ValidationError("Use a private administrator password.")
                except ValidationError as exc:
                    raise CommandError("An administrator password did not meet the password policy. Import rolled back.") from exc
                user.set_password(password)
                user.save(update_fields=["password"])
            for tenant in Tenant.objects.exclude(logo_path=""):
                png = images[tenant.logo_path]
                if settings.LOGO_STORAGE == "database":
                    StationLogo.all_tenants.create(tenant=tenant, path=tenant.logo_path, image=png)
                else:
                    if default_storage.exists(tenant.logo_path):
                        raise CommandError("A destination logo file already exists. Import refused.")
                    saved = default_storage.save(tenant.logo_path, ContentFile(png))
                    saved_files.append(saved)
                    if saved != tenant.logo_path:
                        raise CommandError("Logo path conflict. Import rolled back.")
            for model in transfer_models():
                if model._base_manager.count() != manifest["counts"].get(model._meta.label_lower, 0):
                    raise CommandError("Imported record count mismatch. Import rolled back.")
            connection.check_constraints()
            from apps.audit.models import PlatformAuditLog
            actor = get_user_model().objects.filter(is_superuser=True, is_active=True).first()
            if actor:
                PlatformAuditLog.objects.create(actor=actor, action="deployment_data_imported", object_id="deployment",
                    changes={"exported_at": manifest["exported_at"], "data_sha256": manifest["data_sha256"], "platform_passwords_rotated": len(passwords)})
    except Exception:
        for path in saved_files:
            default_storage.delete(path)
        raise
    return manifest
