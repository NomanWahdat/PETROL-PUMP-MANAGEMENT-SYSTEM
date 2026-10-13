import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    preferred_language = models.CharField(max_length=2, choices=[("fa", "Dari"), ("ps", "Pashto"), ("en", "English")], default="fa")
