"""Copy the Kauai Bus service alerts into alerts.json for the bus tracker.

thekauaibus.com does not allow other websites to read its data, so a
GitHub Action runs this every 30 minutes and saves the alerts next to
index.html, where the tracker can read them.

Standard library only, so the Action needs no installs.
"""
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "https://www.thekauaibus.com/announcements.data"
OUT = Path(__file__).resolve().parent.parent / "alerts.json"

# turbo-stream special values (React Router data format)
SPECIAL = {-1: None, -2: None, -3: None, -4: None, -5: None, -6: None, -7: None}


def decode(flat):
    """Rebuild the nested data from React Router's flat turbo-stream array."""
    cache = {}

    def val(i):
        if isinstance(i, int) and i < 0:
            return SPECIAL.get(i)
        if i in cache:
            return cache[i]
        raw = flat[i]
        if isinstance(raw, list):
            out = []
            cache[i] = out
            out.extend(val(j) for j in raw)
            return out
        if isinstance(raw, dict):
            out = {}
            cache[i] = out
            for k, v in raw.items():
                out[flat[int(k[1:])]] = val(v)
            return out
        cache[i] = raw
        return raw

    return val(0)


def find_alerts(node):
    """Find the "messages" list (the alerts) anywhere in the page data."""
    if isinstance(node, dict):
        msgs = node.get("messages")
        if isinstance(msgs, list) and all(isinstance(x, dict) for x in msgs):
            return msgs
        for v in node.values():
            found = find_alerts(v)
            if found is not None:
                return found
    elif isinstance(node, list):
        for v in node:
            found = find_alerts(v)
            if found is not None:
                return found
    return None


def main():
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "bus-tracker-alerts"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    # The payload is one JSON array on the first line
    flat = json.loads(body.splitlines()[0])
    data = decode(flat)
    raw_alerts = find_alerts(data)
    if raw_alerts is None:
        # Keep the old file rather than wiping it if the bus site changes format
        print("Could not find alerts in the page data; leaving alerts.json unchanged")
        return 1

    alerts = []
    for a in raw_alerts:
        assign = a.get("assignments") or {}
        routes = []
        for r in assign.get("routes") or []:
            if isinstance(r, dict):
                routes.append({
                    "name": r.get("shortName") or r.get("name") or "",
                    "color": r.get("color") or "#555555",
                    "textColor": r.get("textColor") or "#FFFFFF",
                })
        alerts.append({
            "id": a.get("id"),
            "title": (a.get("name") or a.get("title") or "").strip(),
            "text": (a.get("text") or "").strip(),
            "start": a.get("start"),
            "end": a.get("end"),
            "global": bool(assign.get("global")),
            "routes": routes,
        })

    out = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "https://www.thekauaibus.com/announcements",
        "alerts": alerts,
    }
    # Only rewrite when the alerts changed, so the repo isn't committed every run
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8"))
            if old.get("alerts") == alerts:
                print(f"No change ({len(alerts)} alerts)")
                return 0
        except ValueError:
            pass
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(alerts)} alerts to {OUT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
