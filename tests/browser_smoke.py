"""Optional real-browser local smoke check; requires Playwright + Chromium and tools/dev.py running."""
import json
from pathlib import Path
import shutil
import time
import urllib.request
import uuid
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
config = json.loads((ROOT / "var/config.json").read_text())
admin = json.loads((ROOT / "var/local-admin.json").read_text())
screens = ROOT / "var/screenshots"
screens.mkdir(exist_ok=True)


def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request("http://127.0.0.1:8001" + path, data=data, headers={
        "Content-Type": "application/json", "Authorization": "Bearer " + config["panel"]["MIKA_API_TOKEN"]})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "Horizontal overflow"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True,
                                         args=["--no-sandbox", "--disable-dev-shm-usage"])
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    assert page.goto("http://127.0.0.1:8002/").status == 200
    page.get_by_role("heading", name="Hosting untuk ide yang lebih besar.").wait_for()
    assert page.locator(".pricing-card").count() == 3
    no_overflow(page)
    page.screenshot(path=str(screens / "mychahost-desktop.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    no_overflow(page)
    page.screenshot(path=str(screens / "mychahost-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})
    sample = uuid.uuid4().hex[:8]
    page.goto("http://127.0.0.1:8002/register/")
    page.locator('[name="username"]').fill("smoke_" + sample)
    page.locator('[name="first_name"]').fill("Demo Member")
    page.locator('[name="email"]').fill(f"smoke_{sample}@example.test")
    page.locator('[name="password1"]').fill("Browser-fixture-2048!" + sample)
    page.locator('[name="password2"]').fill("Browser-fixture-2048!" + sample)
    page.get_by_role("button", name="Buat akun").click()
    page.wait_for_url("**/dashboard/")
    page.goto("http://127.0.0.1:8002/checkout/stellar/")
    page.locator('[name="domain"]').fill(f"smoke-{sample}.example.test")
    page.locator('[name="customer_phone"]').fill("081234567890")
    page.locator('[name="agree"]').check()
    page.get_by_role("button", name="Buat invoice").click()
    page.wait_for_url("**/orders/**/")
    page.get_by_role("heading", name="Invoice", exact=True).wait_for()
    page.get_by_text("Pembayaran belum tersedia.", exact=False).wait_for()
    page.screenshot(path=str(screens / "mychahost-invoice.png"), full_page=True)
    page.goto("http://127.0.0.1:8002/tickets/")
    page.locator('[name="subject"]').fill("Bantuan DNS demo")
    page.locator('[name="body"]').fill("Bagaimana mengarahkan domain ke IP server?")
    page.get_by_role("button", name="Kirim tiket").click()
    page.get_by_role("link", name="Bantuan DNS demo").wait_for()
    hosting = api("/api/v1/accounts/", {"external_id": "browser-demo-site", "customer_id": "browser-demo", "email": "demo@example.test",
        "plan": "stellar", "kind": "static", "domain": "demo.mikapanels.test", "days": 30})
    deadline = time.monotonic() + 20
    while hosting["status"] == "queued" and time.monotonic() < deadline:
        time.sleep(.5)
        hosting = api("/api/v1/accounts/browser-demo-site/")
    assert hosting["status"] == "active"
    page.goto("http://127.0.0.1:8001/login/")
    page.locator('[name="username"]').fill(admin["username"])
    page.locator('[name="password"]').fill(admin["password"])
    page.get_by_role("button", name="Masuk ke dashboard").click()
    page.wait_for_url("**/dashboard/")
    page.get_by_role("heading", name="Semua website. Satu kendali.").wait_for()
    page.screenshot(path=str(screens / "mikapanels-dashboard.png"), full_page=True)
    page.goto(f"http://127.0.0.1:8001/accounts/{hosting['id']}/")
    page.locator('[name="filename"]').fill("demo.html")
    page.locator('[name="content"]').fill("<h1>MikaPanels browser smoke</h1>")
    page.get_by_role("button", name="Simpan file").click()
    page.get_by_text("demo.html", exact=True).wait_for()
    page.goto(f"http://127.0.0.1:8001/accounts/{hosting['id']}/?file=demo.html")
    assert page.locator('[name="content"]').input_value() == "<h1>MikaPanels browser smoke</h1>"
    page.screenshot(path=str(screens / "mikapanels-files.png"), full_page=True)
    token = api("/api/v1/accounts/browser-demo-site/sso/", {})["token"]
    customer = browser.new_context(viewport={"width": 1440, "height": 1000})
    customer_page = customer.new_page()
    customer_page.goto("http://127.0.0.1:8002/")
    customer_page.evaluate("""token => {
        const form = document.createElement('form'); form.method = 'POST'; form.action = 'http://127.0.0.1:8001/sso/';
        const input = document.createElement('input'); input.name = 'token'; input.value = token;
        form.appendChild(input); document.body.appendChild(form); form.submit();
    }""", token)
    customer_page.wait_for_url("http://127.0.0.1:8001/dashboard/")
    assert customer_page.locator("tbody tr").count() == 1
    customer_page.goto(f"http://127.0.0.1:8001/accounts/{hosting['id']}/")
    customer_page.get_by_role("heading", name="File manager").wait_for()
    assert not errors, errors
    browser.close()
print("PASS: desktop/mobile layout, registration, checkout, tickets, authenticated panel, API provisioning, file editing, and one-time cross-origin SSO. Screenshots: var/screenshots/")
