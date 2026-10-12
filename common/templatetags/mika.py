from django import template
register = template.Library()


@register.filter
def rupiah(value):
    return "Rp " + f"{int(value):,}".replace(",", ".")
