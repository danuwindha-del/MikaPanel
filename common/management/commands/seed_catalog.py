from django.conf import settings
from django.core.management.base import BaseCommand
from hosting.models import Plan
from storefront.models import Product

CATALOG = [
    ("launch", "Launch", "Langkah pertama ide besar Anda", 19000, 1024, 128, 2, False),
    ("stellar", "Stellar", "Ruang berkembang untuk bisnis Anda", 49000, 5120, 256, 4, True),
    ("nebula", "Nebula", "Kapasitas lebih untuk proyek ambisius", 99000, 15360, 512, 8, False),
]


class Command(BaseCommand):
    help = "Seed default plans/products once; preserve existing customized values"

    def handle(self, *args, **options):
        for slug, name, tagline, price, disk, memory, workers, featured in CATALOG:
            if settings.SERVICE == "panel":
                Plan.objects.get_or_create(slug=slug, defaults={"name": name, "disk_mb": disk, "memory_mb": memory, "php_workers": workers})
            else:
                Product.objects.get_or_create(slug=slug, defaults={"name": name, "tagline": tagline, "price": price,
                    "disk_mb": disk, "memory_mb": memory, "php_workers": workers, "panel_plan": slug, "featured": featured})
        self.stdout.write(self.style.SUCCESS(f"Catalog ready: {settings.SERVICE}"))
