"""External probes and a static status snapshot. Python standard library only."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import secrets
import shutil
import socket
import struct
import sys
import time
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


TARGETS = {
    "dashboard": ("پنل کاربری", "https://panel.gerdoo.cloud"),
    "k8s_gateway": ("دسترسی به اپلیکیشن‌ها و وب‌سایت‌ها", "https://edge-health.gerdoo.app/healthz"),
    "k8s_cluster": ("استقرار و به‌روزرسانی اپلیکیشن‌ها", None),
    "dns": ("دامنه‌ها", "109.122.240.83"),
}
TEHRAN = ZoneInfo("Asia/Tehran")
HISTORY_URL = "https://api.gerdoo.cloud/api/status/history"


def history_uptime(key, now, history, spans, incidents):
    start = datetime.combine(now.astimezone(TEHRAN).date() - timedelta(days=89),
                             datetime.min.time(), TEHRAN)
    total = max(1, math.ceil((now - start).total_seconds() / 3600))

    def hours(intervals):
        hit = set()
        for begin, end in intervals:
            begin, end = max(begin, start), min(end, now)
            if end > begin:
                first = int((begin - start).total_seconds() // 3600)
                last = math.ceil((end - start).total_seconds() / 3600)
                hit.update(range(first, last))
        return hit

    declared = [(datetime.fromisoformat(i["started_at"]),
                 datetime.fromisoformat(i["resolved_at"]) if i.get("resolved_at") else now)
                for i in incidents if i["impact"] != "maintenance"
                and (not i["components"] or key in i["components"])]
    original_hours = hours(declared)
    extra = 0
    for component in history.get("components", []):
        if component["key"] == key and component.get("uptime") is not None:
            at = datetime.fromisoformat(history["generated_at"])
            original_start = datetime.combine(at.astimezone(TEHRAN).date() - timedelta(days=89),
                                              datetime.min.time(), TEHRAN)
            original_total = max(1, math.ceil((at - original_start).total_seconds() / 3600))
            # The export contains a percentage, not individual historical outage spans.
            extra = max(0, round(original_total * (100 - component["uptime"]) / 100) - len(original_hours))
    external = [(datetime.fromisoformat(a), datetime.fromisoformat(b)) for a, b in spans]
    return max(0, 100 * (total - len(hours(declared + external)) - extra) / total)


def dns_probe(server):
    ident = secrets.randbelow(65536)
    question = b"".join(bytes([len(p)]) + p.encode("ascii") for p in "gerdoo.cloud".split("."))
    packet = struct.pack("!6H", ident, 0, 1, 0, 0, 0) + question + b"\0\0\1\0\1"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(8)
        sock.connect((server, 53))
        sock.send(packet)
        reply = sock.recv(4096)
    rid, flags, _, answers, _, _ = struct.unpack("!6H", reply[:12])
    if rid != ident or not flags & 0x8000 or flags & 0x020F or not answers:
        raise ValueError("DNS did not return a successful, complete answer")


def probe(key):
    start = time.monotonic()
    # Retry a failed request once; a single network blip is not an outage.
    for attempt in range(2):
        try:
            target = TARGETS[key][1]
            if key == "dns":
                dns_probe(target)
            else:
                request = Request(target, headers={"User-Agent": "Gerdoo-External-Status/1.0"})
                with urlopen(request, timeout=8) as response:
                    if not 200 <= response.status < 400:
                        raise ValueError("HTTP check failed")
            return True, round((time.monotonic() - start) * 1000)
        except (OSError, ValueError, struct.error) as error:
            print(f"{key}: attempt {attempt + 1} failed: {error}", file=sys.stderr)
            if attempt == 0:
                time.sleep(2)
    return False, round((time.monotonic() - start) * 1000)


def snapshot(state, results, now, incidents):
    today = now.astimezone(TEHRAN).date()
    dates = [(today - timedelta(days=i)).isoformat() for i in reversed(range(90))]
    components = []
    outages = state.setdefault("_outages", {})
    history = state.get("_history", {})
    for key, (name, _) in TARGETS.items():
        records = state.setdefault(key, {})
        for day in list(records):
            if day not in dates:
                del records[day]
        record = records.setdefault(dates[-1], {"checks": 0, "up": 0})
        ok, latency = results[key]
        if ok is not None:
            record["checks"] += 1
            record["up"] += int(ok)
        spans = outages.setdefault(key, [])
        spans[:] = [span for span in spans if span[1][:10] >= dates[0]]
        if ok is False:
            spans.append([now.isoformat(), (now + timedelta(minutes=5)).isoformat()])
        days = []
        for date in dates:
            counts = records.get(date, {"checks": 0, "up": 0})
            checks, up = counts["checks"], counts["up"]
            days.append({"date": date, "checks": checks,
                         "uptime": up * 100 / checks if checks else None,
                         "outage_minutes": counts.get("outage_minutes", 0)})
        # Only observed failed samples count; gaps between jobs are unknown.
        if ok is False:
            record["outage_minutes"] = record.get("outage_minutes", 0) + 5
            days[-1]["outage_minutes"] = record["outage_minutes"]
        components.append({"key": key, "name": name, "operational": ok,
                           "latency_ms": latency, "uptime": history_uptime(key, now, history, spans, incidents),
                           "days": days})
    return {"checked_at": now.isoformat(), "generated_at": now.isoformat(),
            "days": 90, "components": components, "incidents": incidents}


def import_history(history):
    return {c["key"]: {d["date"]: {
        "checks": d["checks"],
        "up": round(d["checks"] * (d["uptime"] or 0) / 100),
        "outage_minutes": d["outage_minutes"],
    } for d in c["days"]} for c in history["components"] if c["key"] in TARGETS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--assets", type=Path, default=Path(__file__).parent / "assets")
    args = parser.parse_args()
    source = Path(__file__).parent
    archive = json.loads((source / "history.json").read_text())
    state = json.loads(args.state.read_text()) if args.state.exists() else import_history(archive)
    state.setdefault("_history", archive)
    current = None
    try:
        with urlopen(HISTORY_URL, timeout=8) as response:
            current = json.load(response)
        if not set(TARGETS).issubset({c["key"] for c in current["components"]}):
            raise ValueError("incomplete history export")
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(current["checked_at"])).total_seconds()
        if age > 1200 or age < -60:
            raise ValueError("stale history export")
        state["_history"] = current
    except (OSError, ValueError, KeyError, TypeError) as error:
        current = None
        print(f"History sync unavailable; using retained archive: {error}", file=sys.stderr)
    # Keep the original public history and admin incident updates mirrored externally.
    history = state["_history"]
    for key, records in import_history(history).items():
        existing = state.setdefault(key, {})
        for day, record in records.items():
            if day not in existing:
                existing[day] = record
    original_incidents = {i["id"]: i for i in archive["incidents"]}
    incidents_by_id = {i["id"]: i for i in history["incidents"]}
    for incident in json.loads((source / "incidents.json").read_text()):
        if incident != original_incidents.get(incident["id"]):
            incidents_by_id[incident["id"]] = incident
    incidents = list(incidents_by_id.values())
    external_keys = [key for key in TARGETS if key != "k8s_cluster"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = dict(zip(external_keys, pool.map(probe, external_keys)))
    cluster = next((c for c in (current or {}).get("components", []) if c["key"] == "k8s_cluster"), None)
    results["k8s_cluster"] = (cluster["operational"] if cluster else None, 0)
    data = snapshot(state, results, datetime.now(timezone.utc), incidents)
    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / "index.html", args.output / "index.html")
    shutil.copytree(args.assets / "fonts", args.output / "fonts", dirs_exist_ok=True)
    for name in ("favicon.svg", "favicon.ico"):
        shutil.copyfile(args.assets / name, args.output / name)
    (args.output / "status.json").write_text(json.dumps(data, ensure_ascii=False))
    args.state.parent.mkdir(parents=True, exist_ok=True)
    args.state.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True))
    for key, (ok, _) in results.items():
        print(f"{key}: {'unknown' if ok is None else 'up' if ok else 'down'}")


if __name__ == "__main__":
    main()
