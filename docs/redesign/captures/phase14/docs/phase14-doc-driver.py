import os, sys, json, time, hmac, hashlib, struct, base64
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
    if not ok and r.status_code not in (400, 409, 422, 403):
        print(f"  !! {method} {path} -> {r.status_code}: {r.text[:300]}")
    return j, ok

def totp(secret_b32):
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    ctr = int(time.time()) // 30
    digest = hmac.new(key, struct.pack(">Q", ctr), hashlib.sha1).digest()
    off = digest[-1] & 0xF
    code = (struct.unpack(">I", digest[off:off+4])[0] & 0x7FFFFFFF) % 10**6
    return f"{code:06d}"

def login_owner_aal2():
    """Enroll TOTP for fixture owner, verify, return aal2 token headers."""
    r = httpx.post(f"{SUPA}/auth/v1/token?grant_type=password",
                   headers={"apikey": ANON},
                   json={"email": "demo-owner@fixture.dekopen.local",
                         "password": "Demo-Fixture-2026!"}, timeout=15)
    tok = r.json()["access_token"]
    h = {"apikey": ANON, "Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    # enroll factor
    r = httpx.post(f"{SUPA}/auth/v1/factors", headers=h,
                   json={"factor_type": "totp", "friendly_name": "f14-audit"}, timeout=15)
    fac = r.json()
    fid, secret = fac["id"], fac["totp"]["secret"]
    # challenge + verify
    r = httpx.post(f"{SUPA}/auth/v1/factors/{fid}/challenge", headers=h, json={}, timeout=15)
    chal = r.json()["id"]
    r = httpx.post(f"{SUPA}/auth/v1/factors/{fid}/verify", headers=h,
                   json={"challenge_id": chal, "code": totp(secret)}, timeout=15)
    v = r.json()
    print("  owner verify:", r.status_code, v.get("access_token") is not None)
    tok2 = v["access_token"]
    return {"Authorization": f"Bearer {tok2}",
            "X-Organization-ID": ORG, "Content-Type": "application/json"}

est = login("estimator")
wm = login("manager")
owner = login_owner_aal2()

def stage_project(h, pid):
    j, ok = api(h, "GET", f"/documents/projects/{pid}/inputs/")
    if not ok:
        print(f"  inputs GET failed for {pid}: {j.get('error',{}).get('code')}")
        return None
    body = {
        "payment_terms": "50% anticipo, saldo contra entrega",
        "quotation_valid_until": "2026-12-31",
        "positions": j["positions"],
    }
    j, ok = api(h, "PUT", f"/documents/projects/{pid}/inputs/", body)
    if not ok:
        print(f"  inputs PUT failed: {j.get('error',{}).get('code')} {str(j)[:300]}")
        return None
    j, ok = api(h, "POST", f"/documents/projects/{pid}/preview/", {})
    if not ok:
        print(f"  preview failed: {j.get('error',{}).get('code')}")
        return None
    j, ok = api(h, "POST", f"/documents/projects/{pid}/revision-a/", {})
    if not ok:
        print(f"  apply failed: {j.get('error',{}).get('code')}")
        return None
    j, ok = api(h, "POST", f"/documents/projects/{pid}/freeze/", {})
    if not ok:
        print(f"  freeze failed: {j.get('error',{}).get('code')}")
        return None
    return j

def emit_doc(h, pvid, dtype, fmt="PDF", order_id=None):
    body = {"document_type": dtype, "format": fmt, "project_version_id": pvid}
    if order_id:
        body["order_id"] = order_id
    j, ok = api(h, "POST", "/documents/artifacts/", body)
    if not ok:
        print(f"  !! {dtype} {fmt} emit failed: {j.get('error',{}).get('code')}")
        return None
    aid = j["id"]
    j, ok = api(h, "POST", f"/documents/artifacts/{aid}/access/", {})
    if not ok:
        print(f"  !! {dtype} access failed")
        return None
    url = j["signed_url"]
    if url.startswith("/"):
        url = SUPA + url
    r = httpx.get(url, timeout=60)
    suffix = {"PDF": "pdf", "XLSX": "xlsx"}.get(fmt, "bin")
    name = f"{dtype}-{str(order_id or pvid)[:8]}.{suffix}"
    path = os.path.join(OUT, name)
    with open(path, "wb") as f:
        f.write(r.content)
    print(f"  {dtype} {fmt} {len(r.content)}B -> {name}")
    return name

def design(w, h):
    return {
        "system_id": "3067da09-3119-5ad0-a1d5-498cd2dfd753",
        "nominal_width_mm": str(w), "nominal_height_mm": str(h), "color": "WHITE",
        "parametric_tree": {
            "id": "m1", "type": "BAY", "opening_type": "FIXED",
            "glass_thickness_mm": "24.00", "glass_spec": "4-16-4 Float Incoloro",
            "glass_article_sku": "VIDRIO-BASE",
        },
    }

# ---------- 100-position quote ----------
print("== 100-pos quote ==")
proj, ok = api(est, "GET", "/projects/")
big = None
for p in proj.get("items", []):
    if p.get("position_count", 0) >= 90:
        big = p
        break
if not big:
    big, ok = api(est, "POST", "/projects/",
                  {"name": "Cien posiciones f14", "client_name": "Constructora Cien Ltda.",
                   "client_rut": "76.543.210-9", "delivery_address": "Obra Cien, Santiago"})
    print("  project:", big.get("id"), big.get("code"))
    t0 = time.time()
    made = 0
    for i in range(100):
        r, ok = api(est, "POST", f"/projects/{big['id']}/positions/",
                    {"location_tag": f"Vano {i+1:02d}", "quantity": 1,
                     "design": design(600 + (i % 5) * 150, 600 + (i % 4) * 200)})
        if ok:
            made += 1
        else:
            print(f"  pos {i} failed: {r.get('error',{}).get('code')} {str(r)[:200]}")
            if i < 3:
                break
    print(f"  created {made} positions in {time.time()-t0:.1f}s")
    big["id"] = big["id"] if isinstance(big, dict) else None
else:
    print("  reuse", big["id"], big["position_count"])

vid100 = None
det, ok = api(est, "GET", f"/projects/{big['id']}/")
print("  position_count now:", det.get("position_count"))
if det.get("position_count", 0) == 0:
    stage = stage_project(est, big["id"])
    if stage:
        det, ok = api(est, "GET", f"/projects/{big['id']}/")
for v in det.get("versions", []):
    if v.get("revision_code") == "REV-A":
        vid100 = v["id"]
if vid100:
    emit_doc(est, vid100, "DOC-01")

# ---------- VIVIENDA revision docs ----------
print("== VIVIENDA revision docs ==")
VIV_VID = "f0d6d5e6-9ac2-4e94-ab9f-2ddc71fd455a"
for dtype, h in [("DOC-05", wm), ("DOC-07", owner)]:
    emit_doc(h, VIV_VID, dtype)

# ---------- Purchasing flow -> order-scoped docs ----------
print("== purchasing -> DOC-02/04/08 ==")
vid = VIV_VID
state, ok = api(wm, "GET", f"/purchasing/versions/{vid}/")
if ok:
    reqs = state.get("requirements", [])
    by_type = {}
    for r in reqs:
        by_type.setdefault(r["order_type"], []).append(r)
    print("  requirements by type:", {k: len(v) for k, v in by_type.items()})
    for otype, items in by_type.items():
        keys = [r["requirement_key"] for r in items]
        j, ok = api(wm, "POST", f"/purchasing/versions/{vid}/eligibilities/", {
            "order_type": otype,
            "supplier_identity": f"Prov {otype[-6:]}",
            "supplier_name": f"Proveedor Fixture {otype}",
            "supplier_details": {"address": "Av. Industrial 123, Santiago",
                                 "email": "ventas@prov.example", "phone": "+5622345678",
                                 "tax_id": "76.111.222-3"},
            "eligible_requirement_keys": keys,
            "evidence": {"basis": "Lista de precios vigente fixture", "reference": "LP-2026"},
            "version": 1, "confirmed": True})
        if not ok:
            print(f"  !! eligibility {otype}: {j.get('error',{}).get('code')} {str(j)[:250]}")
            continue
        elig = j.get("supplier_eligibility_id") or j.get("id") or (j.get("eligibility") or {}).get("id")
        print(f"  eligibility {otype}: {elig}")
        for r in items:
            a, ok = api(wm, "PUT", f"/purchasing/requirements/{r['id']}/allocation/",
                        {"supplier_eligibility_id": elig})
            if not ok:
                print(f"    !! alloc {r['id'][:8]}: {a.get('error',{}).get('code')}")
        c, ok = api(wm, "POST", f"/purchasing/versions/{vid}/confirm/",
                    {"order_type": otype, "confirmed": True})
        if ok:
            orders = c.get("orders") or c.get("_list") or []
            print(f"  confirmed {otype}: {len(orders)} orders")
            for o in orders:
                oid = o["id"] if isinstance(o, dict) else o
                s, ok2 = api(wm, "POST", f"/purchasing/orders/{oid}/send/",
                             {"confirmed": True, "expected_at": "2026-10-15",
                              "sent_to": "ventas@prov.example"})
                print(f"    sent {oid} -> {s.get('order_status') or s.get('status')}")
        else:
            print(f"  !! confirm {otype}: {c.get('error',{}).get('code')} {str(c)[:250]}")

    # fetch order list + emit order docs
    oj, ok = api(wm, "GET", "/purchasing/orders/")
    orders = oj.get("orders", []) if isinstance(oj, dict) else oj
    by = {}
    for o in orders:
        by.setdefault(o.get("order_type"), []).append(o)
    def emit_order(dtype, otype, fmts=("PDF",)):
        for o in by.get(otype, [])[:1]:
            for fmt in fmts:
                emit_doc(wm, vid, dtype, fmt, order_id=o["id"])
    emit_order("DOC-04", "SUPPLIER_PROFILE_PO")
    emit_order("DOC-02", "SUPPLIER_GLASS_PO", ("PDF", "XLSX"))
    for t in ("SUPPLIER_HARDWARE_PO", "SUPPLIER_PANEL_PO"):
        if by.get(t):
            emit_order("DOC-08", t, ("PDF", "XLSX"))
            break

# ---------- Production pack docs on VIVIENDA work orders ----------
print("== production packs ==")
woj, ok = api(wm, "GET", "/production/orders/")
wos = woj.get("orders", []) if isinstance(woj, dict) else woj
viv_wos = [w for w in wos if "P-000001" in w.get("order_code", "")]
print(f"  {len(viv_wos)} VIVIENDA WOs")
for w in viv_wos[:2]:
    oid = w["id"]
    for ep, label in [("cut-pack", "cutpack"), ("production-pack", "prodpack")]:
        r = httpx.get(f"{BASE}/production/orders/{oid}/{ep}/", headers=wm, timeout=90)
        if r.status_code == 200 and r.content[:5] == b"%PDF-":
            name = f"{label}-{w['order_code']}.pdf"
            with open(os.path.join(OUT, name), "wb") as f:
                f.write(r.content)
            print(f"  {label} {w['order_code']}: {len(r.content)}B")
        else:
            print(f"  !! {label} {w['order_code']}: {r.status_code} {r.text[:150]}")
    lab, ok = api(wm, "GET", f"/production/orders/{oid}/labels/")
    if ok:
        name = f"labels-{w['order_code']}.json"
        with open(os.path.join(OUT, name), "w") as f:
            json.dump(lab, f, indent=1, default=str)
        print(f"  labels {w['order_code']}: {len(json.dumps(lab))}B")

# dispatch note on any dispatched order
disp = [w for w in wos if w.get("status") in ("DISPATCHED", "PARTIALLY_DISPATCHED", "DELIVERED", "INSTALLED")]
for w in disp[:2]:
    oid = w["id"]
    dn, ok = api(wm, "GET", f"/production/orders/{oid}/dispatch-note/")
    print(f"  dispatch-note {w['order_code']} ({w['status']}): {str(dn)[:200]}")

print("DONE")
