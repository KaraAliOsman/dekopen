import os, sys, json, time
import httpx

OUT = "/home/ubuntu/phase14-docs/pdfs"
os.makedirs(OUT, exist_ok=True)
ORG = "548b9ce5-746b-5a4a-9127-733c4dcd0582"
ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"
BASE = "http://127.0.0.1:8000/api/v1"
SUPA = "http://127.0.0.1:25321"

def login(user):
    r = httpx.post(f"{SUPA}/auth/v1/token?grant_type=password",
                   headers={"apikey": ANON},
                   json={"email": f"demo-{user}@fixture.dekopen.local",
                         "password": "Demo-Fixture-2026!"}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}",
            "X-Organization-ID": ORG, "Content-Type": "application/json"}

def api(h, method, path, body=None, timeout=60):
    r = httpx.request(method, f"{BASE}{path}", headers=h, json=body, timeout=timeout)
    try:
        j = r.json()
    except Exception:
        j = {"_raw": r.text[:400]}
    if isinstance(j, list):
        j = {"_list": j}
    j["_status"] = r.status_code
    ok = 200 <= r.status_code < 300 and "error" not in j
    if not ok:
        print(f"  !! {method} {path} -> {r.status_code}: {str(j)[:260]}")
    return j, ok

wm = login("manager")
op = login("operator")

# ---------- receive all sent POs fully ----------
oj, ok = api(wm, "GET", "/purchasing/orders/")
orders = (oj.get("orders") or []) if isinstance(oj, dict) else []
for o in orders:
    if o.get("status") != "SENT":
        continue
    oid = o["id"]
    rcv, ok = api(wm, "GET", f"/inventory/orders/{oid}/receiving/")
    if not ok:
        continue
    lines = [{"order_line_id": l["id"], "received_qty": str(l["outstanding_qty"])}
             for l in rcv.get("lines", []) if float(l["outstanding_qty"]) > 0]
    if not lines:
        print(f"  order {oid[:8]} already received")
        continue
    j, ok = api(wm, "POST", f"/inventory/orders/{oid}/receipts/",
                {"receipt_key": f"f14-{oid[:8]}", "lines": lines})
    print(f"  received {oid[:8]} ({o.get('order_type')}): {len(lines)} lines ok={ok}")

# ---------- recheck + walk OT-01 ----------
wos = api(wm, "GET", "/production/orders/")[0].get("orders", [])
wo = [w for w in wos if w["order_code"] == "OT-P-000001-REV-A-01"][0]
oid = wo["id"]
api(wm, "POST", f"/production/orders/{oid}/material-recheck/", {})
d, ok = api(wm, "GET", f"/production/orders/{oid}/")
print("WO:", d["order_code"], d["status"], "shortage:", d.get("shortage"))

steps = d.get("steps") or d.get("payload", {}).get("steps") or []
if not steps:
    # try detail sub-resource
    print("keys:", list(d.keys()))
    print(json.dumps(d, default=str)[:800])
    sys.exit(1)

for s in steps:
    sid = s["id"]
    code = s.get("code") or s.get("step_code")
    state = s.get("state") or s.get("status")
    if state in ("DONE", "COMPLETED", "SKIPPED"):
        continue
    j, ok = api(op, "POST", f"/production/steps/{sid}/transition/", {"action": "START"})
    if not ok:
        print(f"  START {code} failed")
        continue
    done_body = {"action": "COMPLETE"}
    if code == "QC":
        done_body["qc_result"] = "PASS"
    j, ok = api(op, "POST", f"/production/steps/{sid}/transition/", done_body)
    print(f"  step {code}: {'ok' if ok else 'FAIL'}")

d, ok = api(wm, "GET", f"/production/orders/{oid}/")
print("after steps:", d["status"], "done:", d.get("steps_done"), "/", d.get("steps_total"),
      "dispatch_ready:", d.get("dispatch_ready"))

# ---------- packing → labels → dispatch → note ----------
j, ok = api(wm, "POST", f"/production/orders/{oid}/packing/")
print("packing:", "ok" if ok else "fail")
lab, ok = api(wm, "GET", f"/production/orders/{oid}/labels/")
if ok:
    with open(os.path.join(OUT, f"labels-{d['order_code']}.json"), "w") as f:
        json.dump(lab, f, indent=1, default=str)
    print("labels:", len(json.dumps(lab)), "B json")

j, ok = api(wm, "POST", f"/production/orders/{oid}/dispatch/",
            {"note": "Despacho f14"})
print("dispatch:", "ok" if ok else "fail", str(j)[:120])

dn, ok = api(wm, "GET", f"/production/orders/{oid}/dispatch-note/")
print("dispatch-note list:", str(dn)[:400])
# find signed url
def grab_signed(obj):
    if isinstance(obj, dict):
        for k in ("signed_url", "tributario_signed_url"):
            if obj.get(k):
                return obj[k]
        for v in obj.values():
            u = grab_signed(v)
            if u:
                return u
    if isinstance(obj, list):
        for v in obj:
            u = grab_signed(v)
            if u:
                return u
    return None
url = grab_signed(dn)
if url:
    if url.startswith("/"):
        url = SUPA + url
    r = httpx.get(url, timeout=60)
    if r.content[:5] == b"%PDF-":
        name = f"dispatch-note-{d['order_code']}.pdf"
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(r.content)
        print(f"  dispatch note pdf {len(r.content)}B -> {name}")
    else:
        print("  signed url non-pdf:", r.status_code, r.text[:150])
print("DONE")
