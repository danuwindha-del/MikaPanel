"""Optional browser check for administrator-created hosting. Requires local tools/dev.py."""
import json
from pathlib import Path
import shutil
import time
import uuid
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
admin = json.loads((ROOT / "var/local-admin.json").read_text())
screens = ROOT / "var/screenshots"
screens.mkdir(exist_ok=True)
domain = f"manual-{uuid.uuid4().hex[:8]}.example.test"

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True,
                                         args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8001/login/")
    page.locator('[name="username"]').fill(admin["username"])
    page.locator('[name="password"]').fill(admin["password"])
    page.get_by_role("button", name="Masuk ke dashboard").click()
    page.wait_for_url("**/dashboard/")
    page.get_by_role("link", name="Buat hosting").click()
    page.get_by_role("heading", name="Buat hosting tanpa pembayaran").wait_for()
    assert page.locator('[name="owner"] option:checked').inner_text() == "admin"
    page.screenshot(path=str(screens / "mikapanels-manual-create.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_label("Domain website").fill(domain)
    page.get_by_label("Paket hosting").select_option(label="Stellar")
    page.get_by_label("Jenis website").select_option("static")
    page.get_by_label("Masa aktif (hari)").fill("7")
    page.get_by_role("button", name="Buat & antrekan hosting").click()
    page.wait_for_url("**/accounts/*/")
    page.get_by_role("heading", name=domain, exact=True).wait_for()
    page.get_by_text("Akun hosting dibuat tanpa pembayaran", exact=False).wait_for()
    deadline = time.monotonic() + 20
    while page.locator(".badge").inner_text() != "Aktif" and time.monotonic() < deadline:
        time.sleep(.5)
        page.reload()
    assert page.locator(".badge").inner_text() == "Aktif"
    page.get_by_role("heading", name="File manager", exact=True).wait_for()
    page.get_by_role("button", name="File baru").click()
    page.locator('#new-file-dialog [name="filename"]').fill("manual.html")
    page.locator('#new-file-dialog [name="content"]').fill("<h1>Manual hosting works</h1>")
    page.get_by_role("button", name="Simpan file →").click()
    page.locator('tr[data-file-name="manual.html"]').wait_for()
    page.screenshot(path=str(screens / "mikapanels-manual-active.png"), full_page=True)
    page.goto("http://127.0.0.1:8001/admin/hosting/account/add/")
    assert page.locator('[name="days"]').count() == 1
    page.screenshot(path=str(screens / "mikapanels-admin-create.png"), full_page=True)
    browser.close()
print("PASS: staff dashboard form, mobile layout, manual account queued/activated by worker, file editing, and admin add form.")
