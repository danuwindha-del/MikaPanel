from django.core.management.base import BaseCommand
from hosting.telemetry import collect_all


class Command(BaseCommand):
    help = "Collect actual Linux server and website usage telemetry"

    def handle(self, *args, **options):
        collect_all()
        self.stdout.write("Telemetry collected from available Linux counters and website logs")
