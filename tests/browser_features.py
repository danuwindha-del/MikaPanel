"""Optional browser coverage for the redesigned hosting workspace (local demo only)."""
import json
from pathlib import Path
import shutil
import time
import uuid
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
config = json.loads((ROOT / "var/config.json").read_text())
admin = json.loads((ROOT / "var/local-admin.json").read_text())
screens = ROOT / "var/screenshots"; screens.mkdir(exist_ok=True)
sample = uuid.uuid4().hex[:6]
payload = {"external_id": "features-" + sample, "customer_id": "features-" + sample, "email": "features@example.test",
    "plan": "stellar", "kind": "php", "domain": f"features-{sample}.example.test", "days": 7}
request = urllib.request.Request("http://127.0.0.1:8001/api/v1/accounts/", json.dumps(payload).encode(),
    {"Content-Type": "application/json", "Authorization": "Bearer " + config["panel"]["MIKA_API_TOKEN"]})
with urllib.request.urlopen(request) as response:
    account = json.load(response)
base = f"http://127.0.0.1:8001/accounts/{account['id']}/"


def no_overflow(page):
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), page.url


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto("http://127.0.0.1:8001/login/")
    page.locator('[name="username"]').fill(admin["username"])
    page.locator('[name="password"]').fill(admin["password"])
    page.get_by_role("button", name="Masuk ke dashboard").click()
    page.wait_for_url("**/dashboard/")
    page.goto(base)
    deadline = time.monotonic() + 20
    while page.locator(".badge").first.inner_text() != "Aktif":
        assert time.monotonic() < deadline, "Provisioning deadline exceeded"
        time.sleep(.5); page.reload()
    page.goto(base + "files/manage/")
    page.get_by_role("button", name="Folder baru").click()
    page.locator('#folder-dialog [name="folder_name"]').fill("assets")
    page.get_by_role("button", name="Buat folder").click()
    page.locator('tr[data-file-name="assets"] .file-name').click()
    page.get_by_role("button", name="File baru").click()
    page.locator('#new-file-dialog [name="filename"]').fill("assets/main.php")
    code = '<?php\n// MikaPanels editor\necho "MychaHost";\n'
    page.locator('#new-file-dialog [name="content"]').fill(code)
    page.get_by_role("button", name="Simpan file →").click()
    page.locator('tr[data-file-name="main.php"]').get_by_role("link", name="Edit", exact=True).click()
    editor = page.locator("#edit-file-dialog")
    assert editor.locator('[name="content"]').input_value() == code
    assert editor.locator(".code-keyword").count() > 0
    page.screenshot(animations="disabled", path=str(screens / "mikapanels-code-editor.png"))
    page.set_viewport_size({"width": 390, "height": 844}); no_overflow(page)
    page.screenshot(animations="disabled", path=str(screens / "mikapanels-editor-mobile.png"))
    editor.get_by_role("button", name="Tutup editor").click()
    page.get_by_role("button", name="Buka navigasi").click()
    assert page.locator(".sidebar").is_visible()
    page.get_by_role("button", name="Tutup navigasi").click(position={"x": 350, "y": 10})
    assert "menu-open" not in page.locator("body").get_attribute("class")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(base + "dns/")
    page.locator('[name="kind"]').select_option("TXT")
    page.locator('[name="name"]').fill("_verify")
    page.locator('[name="value"]').fill('MychaHost DNS "verified"')
    page.locator('[name="ttl"]').fill("600")
    page.get_by_role("button", name="Simpan & publikasikan →").click()
    row = page.get_by_role("row").filter(has_text="_verify")
    row.get_by_role("link", name="Edit", exact=True).click()
    assert page.locator('[name="value"]').input_value() == 'MychaHost DNS "verified"'
    page.locator('[name="ttl"]').fill("3600")
    page.get_by_role("button", name="Simpan & publikasikan →").click()
    assert page.get_by_role("row").filter(has_text="_verify").get_by_role("cell", name="3600", exact=True).count() == 1
    page.screenshot(animations="disabled", path=str(screens / "mikapanels-dns.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844}); no_overflow(page)
    page.screenshot(animations="disabled", path=str(screens / "mikapanels-dns-mobile.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto(base + "databases/")
    page.locator('#database-form [name="label"]').fill("wordpress")
    page.locator('#database-form [name="password"]').fill("Browser-database-fixture-2048!")
    page.get_by_role("button", name="Buat & antrekan database →").click()
    deadline = time.monotonic() + 20
    while page.get_by_role("row").filter(has_text="wordpress").locator(".badge").inner_text() != "demo":
        assert time.monotonic() < deadline
        time.sleep(.5); page.reload()
    page.screenshot(animations="disabled", path=str(screens / "mikapanels-databases.png"), full_page=True)
    page.goto(base + "security/")
    page.locator('[name="network"]').fill("203.0.113.42")
    page.locator('[name="note"]').fill("Browser verification")
    page.get_by_role("button", name="Tambahkan aturan blokir →").click()
    page.get_by_role("cell", name="203.0.113.42/32").wait_for()
    for module in ["security", "ssl", "statistics"]:
        assert page.goto(base + module + "/").status == 200
        no_overflow(page)
        page.set_viewport_size({"width": 390, "height": 844}); no_overflow(page)
        page.set_viewport_size({"width": 1440, "height": 1000})
    page.goto("http://127.0.0.1:8001/notifications/")
    page.get_by_role("heading", name="Notifikasi", exact=True).wait_for()
    page.get_by_role("button", name="Tandai semua dibaca").click()
    assert page.locator(".notification-row.unread").count() == 0
    page.goto("http://127.0.0.1:8001/profile/")
    assert page.get_by_role("heading", name="Profil Saya", exact=True).count() == 1
    assert not errors, errors
    browser.close()
print("PASS: folder creation, nested file save/reopen, syntax editor, mobile navigation, DNS create/edit, database queue, security, SSL/statistics pages, own notification inbox, and profile.")
