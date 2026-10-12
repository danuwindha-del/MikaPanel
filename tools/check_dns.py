#!/usr/bin/env python3
"""Read-only check of NS addresses, BIND zone, UDP/TCP, and public delegation."""
import argparse
import ipaddress
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from hosting.dns_wire import query
if __package__:
    from .system_services import load_environment
else:
    from system_services import load_environment


def check_dns(values, domain=None, resolver="1.1.1.1"):
    server = str(ipaddress.ip_address(values["MIKA_SERVER_IP"]))
    ipaddress.ip_address(resolver)
    primary = values.get("MIKA_DNS_PRIMARY", "ns1.mychahost.my.id").lower().rstrip(".")
    secondary = values.get("MIKA_DNS_SECONDARY", "ns2.mychahost.my.id").lower().rstrip(".")
    port = int(values.get("MIKA_DNS_PORT", "53"))
    failures = 0
    for name in [primary, secondary]:
        try:
            response = query(resolver, name, "A", recursive=True)
            addresses = [r["value"] for r in response["records"] if r["section"] == "answer" and r["type"] == "A" and r["name"] == name]
            ok = response["status"] == "NOERROR" and set(addresses) == {server}
            print(f"NS A {name}: {', '.join(addresses) if addresses else response['status'] + ' / tidak ada A'} — {'OK' if ok else 'PERLU DIPERBAIKI'}")
            if not ok:
                print(f"  Tambahkan A ke {server} pada DNS domain nameserver; pilih DNS only, bukan proxy HTTP.")
            failures += int(not ok)
        except (OSError, ValueError) as exc:
            failures += 1
            print(f"NS A {name}: pemeriksaan gagal ({type(exc).__name__}); belum dapat memastikan alamat publik.")
    if domain:
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", domain):
            raise ValueError("Invalid domain")
        for address in ["127.0.0.1", server]:
            for tcp in [False, True]:
                protocol = "TCP" if tcp else "UDP"
                try:
                    response = query(address, domain, "SOA", port=port, tcp=tcp)
                    soa = [r for r in response["records"] if r["section"] == "answer" and r["type"] == "SOA" and r["name"] == domain]
                    ok = response["status"] == "NOERROR" and response["authoritative"] and bool(soa)
                    print(f"Zone {domain} @{address} {protocol}: {response['status']} / {'authoritative OK' if ok else 'BELUM SIAP'}")
                    failures += int(not ok)
                except (OSError, ValueError) as exc:
                    failures += 1
                    print(f"Zone {domain} @{address} {protocol}: gagal ({type(exc).__name__})")
        try:
            response = query(resolver, domain, "NS", recursive=True)
            names = {r["value"] for r in response["records"] if r["section"] == "answer" and r["type"] == "NS" and r["name"] == domain}
            ok = names == {primary, secondary}
            print(f"NS publik {domain}: {', '.join(sorted(names)) or response['status'] + ' / tidak ada jawaban NS'}")
            if not ok:
                print("  Periksa nameserver di registrar serta cache delegasi; mengubah record panel tidak mengubah registrar.")
                failures += 1
        except (OSError, ValueError) as exc:
            failures += 1
            print(f"NS publik {domain}: pemeriksaan gagal ({type(exc).__name__})")
    print("Kueri ini dijalankan dari VPS. Akses inbound TCP/UDP 53 dari Internet dan firewall provider perlu diuji dari jaringan lain.")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", help="Existing main hosting domain to check")
    parser.add_argument("--resolver", default="1.1.1.1")
    options = parser.parse_args()
    values = load_environment(Path("/etc/mikapanels/panel.env"))
    return int(bool(check_dns(values, options.domain, options.resolver)))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError):
        raise SystemExit("Konfigurasi belum dapat dibaca/valid. Jalankan melalui sudo pada VPS instalasi MikaPanels.")
