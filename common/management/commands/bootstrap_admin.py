import os
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create admin once using MIKA_BOOTSTRAP_EMAIL / MIKA_BOOTSTRAP_PASSWORD"

    def handle(self, *args, **options):
        if User.objects.filter(username="admin").exists():
            self.stdout.write("Existing administrator preserved")
            return
        email = os.getenv("MIKA_BOOTSTRAP_EMAIL", "")
        password = os.getenv("MIKA_BOOTSTRAP_PASSWORD", "")
        if not email or not password:
            raise CommandError("Bootstrap credentials required")
        validate_password(password)
        User.objects.create_superuser(username="admin", email=email, password=password)
        self.stdout.write("Administrator created")
