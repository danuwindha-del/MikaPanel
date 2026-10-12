"""Bounded DNS client for authoritative readiness checks (standard library only)."""
import ipaddress
import re
import secrets
import socket
import struct

TYPES = {"A": 1, "NS": 2, "CNAME": 5, "SOA": 6, "AAAA": 28}
RCODES = {0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN", 4: "NOTIMP", 5: "REFUSED"}


def encode_name(name):
    labels = name.rstrip(".").split(".") if name.rstrip(".") else []
    encoded = []
    for label in labels:
        label = label.encode("idna")
        if not 1 <= len(label) <= 63 or not re.fullmatch(rb"[a-zA-Z0-9_-]+", label):
            raise ValueError("Invalid DNS name")
        encoded.append(bytes([len(label)]) + label)
    data = b"".join(encoded) + b"\0"
    if len(data) > 255:
        raise ValueError("DNS name too long")
    return data


def parse_response(data, identifier, name, kind):
    if len(data) < 12:
        raise ValueError("Short DNS response")
    received, flags, questions, answers, authority, additional = struct.unpack("!6H", data[:12])
    if received != identifier or not flags & 0x8000 or questions != 1 or answers + authority + additional > 512:
        raise ValueError("Invalid DNS response")
    if flags & 0x200:
        raise ValueError("Truncated DNS response; retry with TCP")

    def read_name(offset, visited=None):
        visited = set() if visited is None else visited
        labels = []
        while True:
            if offset >= len(data) or offset in visited or len(visited) > 128:
                raise ValueError("Invalid DNS name compression")
            visited.add(offset)
            length = data[offset]
            if length == 0:
                return ".".join(labels).lower(), offset + 1
            if length & 0xC0 == 0xC0:
                if offset + 1 >= len(data):
                    raise ValueError("Short DNS pointer")
                pointer = ((length & 63) << 8) | data[offset + 1]
                suffix, _ = read_name(pointer, visited)
                labels.append(suffix)
                return ".".join(labels).lower(), offset + 2
            if length > 63 or offset + 1 + length > len(data):
                raise ValueError("Invalid DNS label")
            offset += 1
            labels.append(data[offset:offset + length].decode("ascii"))
            offset += length

    question, offset = read_name(12)
    if question != name.rstrip(".").encode("idna").decode().lower() or offset + 4 > len(data):
        raise ValueError("DNS question mismatch")
    if struct.unpack("!HH", data[offset:offset + 4]) != (TYPES[kind], 1):
        raise ValueError("DNS type mismatch")
    offset += 4
    records = []
    for section, count in [("answer", answers), ("authority", authority), ("additional", additional)]:
        for _ in range(count):
            owner, offset = read_name(offset)
            if offset + 10 > len(data):
                raise ValueError("Short DNS record")
            rtype, rclass, ttl, length = struct.unpack("!HHIH", data[offset:offset + 10])
            offset += 10
            end = offset + length
            if end > len(data):
                raise ValueError("Short DNS record data")
            value = None
            if rtype in {1, 28}:
                if length != (4 if rtype == 1 else 16):
                    raise ValueError("Invalid DNS address")
                value = str(ipaddress.ip_address(data[offset:end]))
            elif rtype in {2, 5}:
                value, consumed = read_name(offset)
                if consumed > end:
                    raise ValueError("Invalid DNS record name")
            elif rtype == 6:
                primary, consumed = read_name(offset)
                responsible, consumed = read_name(consumed)
                if consumed + 20 != end:
                    raise ValueError("Invalid DNS SOA")
                serial, refresh, retry, expire, minimum = struct.unpack("!5I", data[consumed:end])
                value = {"primary": primary, "responsible": responsible, "serial": serial,
                         "refresh": refresh, "retry": retry, "expire": expire, "minimum": minimum}
            if rclass == 1 and value is not None:
                records.append({"section": section, "name": owner, "type": next(k for k, v in TYPES.items() if v == rtype), "ttl": ttl, "value": value})
            offset = end
    return {"status": RCODES.get(flags & 15, str(flags & 15)), "authoritative": bool(flags & 0x400), "records": records}


def query(server, name, kind="SOA", *, port=53, tcp=False, recursive=False, timeout=2):
    address = ipaddress.ip_address(server)
    identifier = secrets.randbelow(65536)
    packet = struct.pack("!6H", identifier, 0x100 if recursive else 0, 1, 0, 0, 0) + encode_name(name) + struct.pack("!HH", TYPES[kind], 1)
    family = socket.AF_INET6 if address.version == 6 else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM if tcp else socket.SOCK_DGRAM) as connection:
        connection.settimeout(timeout)
        connection.connect((str(address), port))
        if tcp:
            connection.sendall(struct.pack("!H", len(packet)) + packet)
            def read_exact(size):
                data = b""
                while len(data) < size:
                    chunk = connection.recv(size - len(data))
                    if not chunk:
                        raise OSError("DNS TCP connection closed early")
                    data += chunk
                return data
            length = struct.unpack("!H", read_exact(2))[0]
            response = read_exact(length)
        else:
            connection.send(packet)
            response = connection.recv(65535)
    return parse_response(response, identifier, name, kind)


def zone_ready(response, domain, serial, primary):
    return (response["status"] == "NOERROR" and response["authoritative"]
            and any(record["section"] == "answer" and record["name"] == domain
                    and record["type"] == "SOA" and record["value"]["serial"] == serial
                    and record["value"]["primary"] == primary for record in response["records"]))
