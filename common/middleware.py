from django.conf import settings
from django.http import HttpResponseForbidden


class ServiceBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Each process and database has a single service. Do not expose shop models via panel admin or vice versa.
        if request.path.startswith("/admin/") and not request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect("/login/?next=/admin/")
        if request.path.startswith("/admin/") and not request.user.is_staff:
            return HttpResponseForbidden("Administrator only")
        return self.get_response(request)
