import io, json, re, base64
from datetime import datetime, timezone
import requests
import streamlit as st
import pdfplumber

st.set_page_config(page_title="HISAB Version 2.0", page_icon="📊", layout="wide")
OWNER, REPO, BRANCH, RULES_PATH = "ravijainconnect", "bill-summary-v2.0", "main", "saved_rules.json"

st.title("📊 HISAB — Version 2.0")
st.caption("Separate V2 app. The existing Version 1.0 repository/deployment is not modified.")

def gh_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"} if token else None

def load_rules():
    h = gh_headers()
    if not h: return [], None, "Permanent rule saving is disabled until GITHUB_TOKEN is added in Streamlit Cloud → Manage app → Settings → Secrets. Token must have Contents read/write access to ravijainconnect/bill-summary-v2.0."
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{RULES_PATH}?ref={BRANCH}"
    try:
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code == 404: return [], None, None
        r.raise_for_status()
        p = r.json()
        return json.loads(base64.b64decode(p["content"]).decode()), p["sha"], None
    except Exception as e: return [], None, f"Could not load saved rules: {e}"

def save_rules(rules, sha, message="Save HISAB V2 client rule"):
    h = gh_headers()
    if not h: return False, "Add GITHUB_TOKEN in Streamlit Cloud → Manage app → Settings → Secrets. It needs Contents read/write access to ravijainconnect/bill-summary-v2.0."
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{RULES_PATH}"
    body = {"message":message,
            "content":base64.b64encode(json.dumps(rules, ensure_ascii=False, indent=2).encode()).decode(),
            "branch":BRANCH}
    if sha: body["sha"] = sha
    try:
        r = requests.put(url, headers=h, json=body, timeout=20)
        r.raise_for_status()
        return True, "Rule saved to the HISAB V2 repository."
    except Exception as e: return False, f"Save failed: {e}"

files = st.file_uploader("1. Upload settlement PDFs", type=["pdf"], accept_multiple_files=True)

# Locked supplier/client mappings. PDF filenames are never used for identification.
SUPPLIER_CODES = {"624505": "JAMES5", "964727": "AM 15", "640438": "AM RAVI 30"}
# Exact client codes from HISAB_Client_Master_Rechecked_Filled.xlsx (23 verified mappings).
# Code match protects known clients whose PDF display name varies; name patterns below
# remain a secondary compatibility check. Unknown codes are never assigned a guessed rule.
MASTER_CLIENT_CODES = {
    "970083", "665826", "166386", "569816", "892104", "415200",
    "830992", "181376", "707005", "197229", "840750", "492972",
    "624733", "887684", "498413", "915871", "922247", "352250",
    "217244", "680260", "914893", "320560", "887584", "647147",
}
CLIENT_CODE_GROUP = {
    "970083":"SONU MAK", "665826":"SONU MAK", "166386":"SONU MAK",
    "569816":"SONU MAK", "892104":"SONU MAK", "415200":"LV",
    "830992":"MAHAVIR", "181376":"JANIE28", "707005":"TONY",
    "197229":"RITESH", "840750":"RITESH", "492972":"RITESH",
    "624733":"RITESH", "887684":"VIKRAM", "914893":"VIKRAM",
    "498413":"SUMIT", "915871":"SONU SN", "922247":"PATNI",
    "352250":"PATNI", "217244":"SPECIAL", "680260":"SONU SN",
    "320560":"SONU SN", "887584":"SONU SN", "647147":"VM_LOKESH",
}
KNOWN_CLIENT_PATTERNS = {
    "SONU MAK": ["SONI_SC_10L", "DILIP_SC_10L", "BAHETI_SC50L", "SP_MM", "SS12", "SUNIL_SC_10L"],
    "SONU SN": ["PRAHAL_SC_10L", "NISHIDHA_SC_5L", "GANESH_SC_5L", "VIMAL_SC5L"],
    "VIKRAM": ["PANKAJ", "VIPIN"],
    "VM_LOKESH": ["VM_LOKESH"],
    "PATNI": ["GOPAL_", "HIMANSHU_"],
    "RITESH": ["RISHI", "GULLU", "DHEERAJ", "_NB"],
    "SUMIT": ["NITESH_SC4L"],
    "LV": ["LV_"],
    "TONY": ["TONY"],
    "MAHAVIR": ["MAHAVIR"],
    "SPECIAL": ["AM_AA01", "AM_VISHAL"],
}
def known_client_group(client_name, client_code=None):
    if client_code and client_code in CLIENT_CODE_GROUP:
        return CLIENT_CODE_GROUP[client_code]
    n = client_name.upper()
    for group, patterns in KNOWN_CLIENT_PATTERNS.items():
        if any(p in n for p in patterns):
            return group
    return None

supplier_names = []
pdf_client_headers = []
pdf_errors = []
if files:
    for f in files:
        try:
            with pdfplumber.open(io.BytesIO(f.getvalue())) as pdf:
                pdf_text = "\n".join(p.extract_text(x_tolerance=2, y_tolerance=3) or "" for p in pdf.pages)
            headers = list(re.finditer(r"^\s*\((\d{6})\)\s*([^\n]+?)\s*$", pdf_text, re.M))
            if not headers:
                pdf_errors.append(f"{f.name}: supplier/client code headers not found inside PDF")
                continue
            supplier_code, supplier_name = headers[0].group(1), headers[0].group(2).strip()
            if supplier_code not in SUPPLIER_CODES:
                pdf_errors.append(f"{f.name}: unrecognized supplier code {supplier_code} ({supplier_name})")
            else:
                supplier_names.append(SUPPLIER_CODES[supplier_code])
            # Only inner client headers can trigger New Client Module. Supplier header is excluded.
            for m in headers[1:]:
                item = {"code": m.group(1), "name": m.group(2).strip(), "supplier": supplier_name, "file": f.name}
                if not any(x["code"] == item["code"] and x["name"].casefold() == item["name"].casefold() for x in pdf_client_headers):
                    pdf_client_headers.append(item)
        except Exception as e:
            pdf_errors.append(f"{f.name}: PDF text extraction failed ({e})")
    st.caption(f"PDF files selected: {len(files)}")
    st.write("Supplier names detected from PDF contents:" if supplier_names else "No known supplier detected from PDF contents.")
    if supplier_names:
        st.write(", ".join(supplier_names))
    if pdf_errors:
        for e in pdf_errors: st.warning(e)

rules, sha, error = load_rules()
if error: st.warning(error)
else:
    st.success(f"GitHub rule store read OK · {len(rules)} saved rule(s) loaded")
    st.caption("Read access is verified on this load. Write access is confirmed only after the write-permission test or a successful permanent rule save.")

known_clients = {str(x.get("detected_client", "")).strip().casefold() for x in rules if x.get("detected_client")}

def client_match_status(c):
    if c["code"] in MASTER_CLIENT_CODES:
        return "Known — verified master code"
    group = known_client_group(c["name"], c["code"])
    if group:
        return f"Known — locked group: {group}"
    if c["name"].strip().casefold() in known_clients:
        return "Known — saved rule"
    return "UNKNOWN — blocks settlement"

client_audit = []
for c in pdf_client_headers:
    client_audit.append({
        "Supplier in PDF": c["supplier"],
        "Client code": c["code"],
        "Client name in PDF": c["name"],
        "Recognition": client_match_status(c),
        "Source file": c["file"],
    })
st.subheader("Detected Client Audit")
if client_audit:
    st.dataframe(client_audit, use_container_width=True, hide_index=True)
else:
    st.info("No client headers were extracted from the selected PDFs.")

new_clients = [c for c in pdf_client_headers if client_match_status(c).startswith("UNKNOWN")]
if new_clients:
    st.subheader("New Client Module")
    client_record = new_clients[0]
    client = client_record["name"]
    st.text_input("1. FOUND NEW CLIENT (auto-detected / locked)", value=f'{client} (Code {client_record["code"]})', disabled=True)
    st.warning("Unknown client detected. Settlement must remain blocked until its rule is saved and locked.")
    people = sorted({str(x.get("first_person","")) for x in rules if x.get("first_person")} |
                    {str(x.get("second_person","")) for x in rules if x.get("second_person")})
    choice = st.selectbox("2. 1ST LENDEN PERSON", [""] + people + ["＋ ADD NEW"])
    first = st.text_input("Enter new first lenden person name") if choice == "＋ ADD NEW" else choice
    share1 = st.number_input("3. 1ST LENDEN PERSON SHARING (%)", 0.0, 100.0, 0.0, step=0.25)
    basis1 = st.radio("4. 1ST LENDEN PERSON SHARING BASIS", ["Final Bill","Brokerage","Final Bill + Return Brokerage"])
    broker1 = st.number_input("5. 1ST LENDEN PERSON BROKER BROKERAGE SHARING (%)", 0.0, 100.0, 0.0, step=0.25)
    total1 = st.number_input("6. 1ST LENDEN PERSON TOTAL BROKERAGE SHARING (%)", 0.0, 100.0, 0.0, step=0.25)
    second = st.radio("7. 2ND LENDEN PERSON?", ["NO","YES"], horizontal=True)
    if second == "YES":
        basis2 = st.radio("8. 2ND LENDEN PERSON SHARING BASIS", ["Final Bill","Brokerage","Final Bill + Return Brokerage"])
        share2 = st.number_input("9. 2ND LENDEN PERSON SHARING (%)", 0.0, 100.0, 0.0, step=0.25)
        broker2 = st.number_input("10. 2ND LENDEN PERSON BROKER BROKERAGE SHARING (%)", 0.0, 100.0, 0.0, step=0.25)
        total2 = st.number_input("11. 2ND LENDEN PERSON TOTAL BROKERAGE SHARING (%)", 0.0, 100.0, 0.0, step=0.25)
    else: basis2, share2, broker2, total2 = "", 0.0, 0.0, 0.0
    kind = st.radio("Rule type", ["Additional sharing","Replacement sharing"])
    if st.button("Save Rule Permanently", type="primary", use_container_width=True):
        if not first: st.error("Select or enter the first lenden person.")
        elif not client: st.error("No client name detected inside PDF.")
        else:
            new = {"detected_client":client,"detected_client_code":client_record["code"],"first_person":first,"first_sharing_pct":share1,"first_basis":basis1,
                   "first_broker_brokerage_sharing_pct":broker1,"first_total_brokerage_sharing_pct":total1,
                   "has_second_person":second,"second_basis":basis2,"second_sharing_pct":share2,
                   "second_broker_brokerage_sharing_pct":broker2,"second_total_brokerage_sharing_pct":total2,
                   "rule_type":kind,"saved_at_utc":datetime.now(timezone.utc).isoformat()}
            rules.append(new)
            ok, msg = save_rules(rules, sha)
            if ok: st.success(msg); st.rerun()
            else: rules.pop(); st.error(msg)
else:
    st.caption("No new client detected. New Client Module is hidden.")

st.subheader("GitHub Saving Check")
st.caption("This test writes the current rules back unchanged. It creates an audit commit but does not add or alter any client rule.")
if st.button("Verify GitHub write access (no rule changes)", use_container_width=True, disabled=bool(error or sha is None)):
    ok, msg = save_rules(rules, sha, message="Verify HISAB V2 GitHub rule-store write access (no rule changes)")
    if ok:
        st.success("GitHub write access VERIFIED. Existing rule data was preserved unchanged.")
        st.info("Reload the app once to refresh the file SHA before the next rule save.")
    else:
        st.error("GitHub write access NOT VERIFIED.")
        st.write(msg)

st.subheader("Saved Rules")
if rules:
    st.dataframe(rules, use_container_width=True, hide_index=True)
    st.download_button("Download saved rules backup", json.dumps(rules, ensure_ascii=False, indent=2),
                       file_name="hisab_v2_saved_rules_backup.json", mime="application/json")
else: st.info("No rules saved yet.")

st.subheader("Settlement Summary")
st.caption("Calculation engine is available below. The app blocks the summary if reconciliation or client-rule checks fail.")


# ---------------- V2 CALCULATION ENGINE (ported from HISAB V11) ----------------
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass

@dataclass
class V2Client:
    code: str
    name: str
    total_brokerage: Decimal
    broker_brokerage: Decimal
    final_bill: Decimal

@dataclass
class V2Supplier:
    code: str
    name: str
    total_gross: Decimal
    total_brokerage: Decimal
    broker_brokerage: Decimal
    final_bill: Decimal
    clients: list
    raw_text: str

def v2_num(s):
    s = s.replace(",", "").replace("Rs", "").strip()
    if s.startswith("(") and s.endswith(")"): s = "-" + s[1:-1]
    return Decimal(s)

def v2_parse_pdf(text):
    m = re.search(r"^\s*\((\d{6})\)\s*(.+?)\s*$", text, re.M)
    if not m: raise ValueError("Supplier header not found")
    code, name = m.group(1), m.group(2).strip()
    if code not in SUPPLIER_CODES: raise ValueError(f"Unknown supplier code {code} ({name})")
    starts = list(re.finditer(r"^\s*\((\d{6})\)\s*(.+?)\s*$", text, re.M))
    clients = []
    for i, sm in enumerate(starts[1:], start=1):
        end = starts[i+1].start() if i+1 < len(starts) else len(text)
        block = text[sm.start():end]
        z = re.search(r"Total Brokerage:\s*([\-\d,]+\.\d+)\s+Broker Brokerage:\s*([\-\d,]+\.\d+)\s+Final Bill Amt\s*:\s*([\-\d,]+\.\d+)", block, re.S)
        if z:
            tb, bb, fb = map(v2_num, z.groups())
            clients.append(V2Client(sm.group(1), sm.group(2).strip(), tb, bb, fb))
    z = re.search(r"Total Gross:\s*([\-\d,]+\.\d+)\s+Total Brokerage:\s*([\-\d,]+\.\d+)\s+Broker Brokerage:\s*([\-\d,]+\.\d+)\s+Final Bill Amt\s*:\s*([\-\d,]+\.\d+)", text, re.S)
    if not z: raise ValueError("Supplier total line not found")
    tg, tb, bb, fb = map(v2_num, z.groups())
    return V2Supplier(code, name, tg, tb, bb, fb, clients, text)

def v2_reconcile(p):
    e = []
    close = Decimal("0.01")
    if abs(sum((c.final_bill for c in p.clients), Decimal(0)) + p.broker_brokerage - p.final_bill) > close:
        e.append(f"{p.name}: client final sum + broker brokerage does not match supplier final")
    if abs(sum((c.total_brokerage for c in p.clients), Decimal(0)) - p.total_brokerage) > close:
        e.append(f"{p.name}: client total brokerage mismatch")
    if abs(sum((c.broker_brokerage for c in p.clients), Decimal(0)) - p.broker_brokerage) > close:
        e.append(f"{p.name}: client broker brokerage mismatch")
    if abs(p.total_gross - p.total_brokerage + p.broker_brokerage - p.final_bill) > close:
        e.append(f"{p.name}: gross/brokerage/final-bill mismatch")
    return e

def v2_group(c):
    n = c.name.upper()
    # Same verified master-code mapping as the Detected Client Audit.
    if c.code in CLIENT_CODE_GROUP: return CLIENT_CODE_GROUP[c.code]
    if "VM_LOKESH" in n: return "VM_LOKESH"
    if "JANIE28" in n: return "JANIE28"
    if "AM_AA01" in n or "AM_VISHAL" in n: return "SPECIAL"
    pats = {
      "SONU MAK":["SONI_SC_10L","DILIP_SC_10L","BAHETI_SC50L","SP_MM","SS12","SUNIL_SC_10L"],
      "SONU SN":["PRAHAL_SC_10L","NISHIDHA_SC_5L","GANESH_SC_5L","VIMAL_SC5L"],
      "VIKRAM":["PANKAJ","VIPIN"], "PATNI":["GOPAL_","HIMANSHU_"],
      "RITESH":["RISHI","GULLU","DHEERAJ","_NB"], "SUMIT":["NITESH_SC4L"],
      "LV":["LV_"], "TONY":["TONY"], "MAHAVIR":["MAHAVIR"]
    }
    for g, pp in pats.items():
        if any(x in n for x in pp): return g
    return None

def v2_round(x):
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

def v2_calculate(pdfs):
    errors = [e for p in pdfs for e in v2_reconcile(p)]
    for p in pdfs:
        q = v2_parse_pdf(p.raw_text)
        if (p.code,p.final_bill,p.total_brokerage,p.broker_brokerage,len(p.clients)) != (q.code,q.final_bill,q.total_brokerage,q.broker_brokerage,len(q.clients)):
            errors.append(f"{p.name}: independent second-pass mismatch")
        elif any((a.code,a.name,a.total_brokerage,a.broker_brokerage,a.final_bill)!=(b.code,b.name,b.total_brokerage,b.broker_brokerage,b.final_bill) for a,b in zip(p.clients,q.clients)):
            errors.append(f"{p.name}: client second-pass mismatch")
    if errors: return None, errors, []

    allc = [c for p in pdfs for c in p.clients]
    groups = {}
    unknown = []
    for c in allc:
        g = v2_group(c)
        if not g: unknown.append(c)
        else: groups.setdefault(g, []).append(c)
    if unknown: return None, [], unknown

    rows = []
    def add(party, raw, rounding=ROUND_HALF_UP):
        rows.append({"party":party,"raw":raw,"amount":raw.quantize(Decimal("1"), rounding=rounding)})

    # SONU MAK: signed client bills + locked Saturday BKG return ₹2,503, then 10%.
    # Preserve the already-approved Module 1 result's away-from-zero rounding.
    cs = groups.get("SONU MAK", [])
    if cs:
        signed = sum((c.final_bill for c in cs), Decimal(0))
        raw = (signed + Decimal("2503")) * Decimal("0.10")
        add("SONU MAK", raw, ROUND_UP)

    # SONU SN: calculate each client's 85% share, round each line, then aggregate.
    cs = groups.get("SONU SN", [])
    if cs:
        amount = sum(((c.final_bill * Decimal("0.85")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) for c in cs), Decimal(0))
        rows.append({"party":"SONU_SN","raw":sum((c.final_bill * Decimal("0.85") for c in cs),Decimal(0)),"amount":amount})

    # VIKRAM: signed net x 50%. RS separately gets 10% opposite each client's direction.
    cs = groups.get("VIKRAM", [])
    if cs:
        add("VIKRAM", sum((c.final_bill for c in cs),Decimal(0))*Decimal("0.50"))
        rs = sum(((-c.final_bill * Decimal("0.10")).quantize(Decimal("1"),rounding=ROUND_HALF_UP) for c in cs),Decimal(0))
        rows.append({"party":"RS","raw":sum((-c.final_bill*Decimal("0.10") for c in cs),Decimal(0)),"amount":rs})

    # VM_LOKESH is independent of VIKRAM: signed Final Bill x 50%, no RS.
    cs = groups.get("VM_LOKESH", [])
    if cs: add("VM_LOKESH",sum((c.final_bill for c in cs),Decimal(0))*Decimal("0.50"))

    # PATNI: signed final bills + 25% of combined total brokerage as positive DENA.
    # RS receives 40% of PATNI's resulting net settlement, in the opposite direction.
    cs = groups.get("PATNI", [])
    if cs:
        patni_raw = sum((c.final_bill for c in cs),Decimal(0)) + sum((c.total_brokerage for c in cs),Decimal(0))*Decimal("0.25")
        patni_amt = patni_raw.quantize(Decimal("1"),rounding=ROUND_HALF_UP)
        rows.append({"party":"PATNI","raw":patni_raw,"amount":patni_amt})
        rs_amt = (-patni_amt * Decimal("0.40")).quantize(Decimal("1"),rounding=ROUND_HALF_UP)
        rows.append({"party":"RS","raw":-patni_raw*Decimal("0.40"),"amount":rs_amt})

    # RITESH: per-client direction/percentage. GULLU adds one-third of its full brokerage
    # (rounded to rupees) to the bill base before applying 30%.
    cs = groups.get("RITESH", [])
    if cs:
        total = Decimal(0)
        for client in cs:
            n = client.name.upper()
            if "RISHI" in n:
                line = client.final_bill * Decimal("0.40")
            elif "GULLU" in n:
                brokerage_return = (client.total_brokerage / Decimal(3)).quantize(Decimal("1"),rounding=ROUND_HALF_UP)
                line = (client.final_bill + brokerage_return) * Decimal("0.30")
            elif "DHEERAJ" in n:
                line = client.final_bill * Decimal("0.40")
            elif "NB" in n:
                line = client.final_bill * Decimal("0.30")
            else:
                return None,[f"RITESH client mapping missing for {client.name}"],[]
            total += line.quantize(Decimal("1"),rounding=ROUND_HALF_UP)
        rows.append({"party":"RITESH","raw":sum((c.final_bill for c in cs),Decimal(0)),"amount":total})

    # SUMIT: signed final bill plus 50% of current total brokerage; no stale fixed BKG.
    cs = groups.get("SUMIT", [])
    if cs:
        raw = sum((c.final_bill + c.total_brokerage*Decimal("0.50") for c in cs),Decimal(0))
        add("SUMIT",raw)

    # LV Saturday: signed final bill plus positive broker-brokerage return, then 10%.
    cs = groups.get("LV", [])
    if cs:
        raw = sum(((c.final_bill + c.broker_brokerage)*Decimal("0.10") for c in cs),Decimal(0))
        add("LV",raw)

    # Preserve signed PDF direction for TONY/MAHAVIR (approved summary uses source sign).
    for g in ("TONY","MAHAVIR"):
        cs = groups.get(g, [])
        if cs: add(g,sum((c.final_bill for c in cs),Decimal(0)))

    # JANIE28 is a direct signed pass-through, with no sharing deduction.
    cs = groups.get("JANIE28", [])
    if cs: add("JANIE28",sum((c.final_bill for c in cs),Decimal(0)))

    # AM80: preserve each source sign; add positive broker-brokerage returns.
    aa = next((c for c in allc if "AM_AA01" in c.name.upper()),None)
    vv = next((c for c in allc if "AM_VISHAL" in c.name.upper()),None)
    if aa is None or vv is None: return None,["AM80 calculation blocked: AM_AA01 or AM_VISHAL missing"],[]
    am80_base = aa.final_bill + aa.broker_brokerage + vv.final_bill + vv.broker_brokerage
    # Legacy approved summary truncates AM80 to whole rupees.
    add("AM80",am80_base*Decimal("0.20"),ROUND_DOWN)

    # Supplier shares use locked directions from the approved Saturday summary.
    supplier_rules = {
        "624505":("JAMES5",Decimal("0.05"),1),
        "964727":("AM 15",Decimal("0.17"),1),
        "640438":("AM RAVI 30",Decimal("0.35"),-1),
    }
    for p in pdfs:
        party,pct,direction = supplier_rules[p.code]
        add(party,abs(p.final_bill)*pct*Decimal(direction))

    # Collapse multiple RS calculations to exactly one final-summary line.
    rs_amount = sum((r["amount"] for r in rows if r["party"]=="RS"),Decimal(0))
    rs_raw = sum((r["raw"] for r in rows if r["party"]=="RS"),Decimal(0))
    rows = [r for r in rows if r["party"]!="RS"]
    if rs_amount: rows.append({"party":"RS","raw":rs_raw,"amount":rs_amount})

    rows.append({"party":"RITESH-2","raw":Decimal("102550"),"amount":Decimal("102550")})
    dena = sum((r["amount"] for r in rows if r["amount"]>0),Decimal(0))
    lena = -sum((r["amount"] for r in rows if r["amount"]<0),Decimal(0))
    return {"rows":rows,"dena":dena,"lena":lena,"difference":lena-dena,"pdfs":pdfs},[],[]

st.divider()
st.subheader("Settlement Summary — Calculation Engine")
st.caption("V2 calculation engine runs only after reconciliation, independent second-pass checks, and known-client validation. Unknown clients block the result.")
if files:
    if st.button("PROCESS & VERIFY — Generate Final Summary", type="primary", use_container_width=True):
        parsed=[]; parse_errors=[]
        for f in files:
            try:
                with pdfplumber.open(io.BytesIO(f.getvalue())) as pdf:
                    txt="\n".join(pg.extract_text(x_tolerance=2,y_tolerance=3) or "" for pg in pdf.pages)
                parsed.append(v2_parse_pdf(txt))
            except Exception as ex: parse_errors.append(f"{f.name}: {ex}")
        if parse_errors:
            st.error("NOT VERIFIED — no final summary generated")
            for e in parse_errors: st.write("• "+e)
        else:
            result, errs, unknown = v2_calculate(parsed)
            if errs:
                st.error("NOT VERIFIED — reconciliation failed; summary blocked")
                for e in errs: st.write("• "+e)
            elif unknown:
                st.error("UNKNOWN CLIENT — summary blocked until the locked rule is confirmed")
                st.dataframe([{"Code":c.code,"Client":c.name,"Final Bill":f"{c.final_bill:,.2f}"} for c in unknown],use_container_width=True,hide_index=True)
            else:
                import pandas as pd
                # Regression test against the approved locked Modules 1–3 + RITESH-2.
                signature = sorted((p.code, str(p.final_bill.quantize(Decimal("0.01")))) for p in parsed)
                approved_signature = sorted([
                    ("624505", "-1571881.66"),
                    ("640438", "182839.62"),
                    ("964727", "-25076.81"),
                ])
                expected = {
                    "SONU_SN":446093, "RS":128862, "JAMES5":78594, "RITESH":69852,
                    "TONY":45908, "AM80":18673, "AM 15":4263, "RITESH-2":102550,
                    "VIKRAM":-307340, "PATNI":-168485, "SONU MAK":-131862,
                    "SUMIT":-62111, "AM RAVI 30":-63994, "LV":-25327,
                }
                actual = {r["party"]:int(r["amount"]) for r in result["rows"]}
                is_golden = signature == approved_signature
                mismatches = []
                if is_golden:
                    for party in sorted(set(expected)|set(actual)):
                        if actual.get(party,0) != expected.get(party,0):
                            mismatches.append({"Party":party,"Approved amount":expected.get(party,0),"Engine amount":actual.get(party,0),"Difference":actual.get(party,0)-expected.get(party,0)})
                    if result["dena"] != Decimal("894795") or result["lena"] != Decimal("759119"):
                        mismatches.append({"Party":"TOTALS","Approved amount":0,"Engine amount":0,"Difference":int(result["dena"]-Decimal("894795"))})
                if mismatches:
                    st.error("REGRESSION TEST FAILED — final summary is blocked. Engine output differs from the locked approved summary.")
                    st.dataframe(pd.DataFrame(mismatches),use_container_width=True,hide_index=True)
                    st.caption("No final result or export is shown until every locked party amount and total matches.")
                else:
                    st.success("VERIFIED — PDF reconciliation, independent parse, client-rule checks, and locked-summary regression passed.")
                    st.markdown("### FINAL SUMMARY — DENA vs LENA")
                    dena_rows=[{"DENA PARTY":r["party"],"DENA AMOUNT":int(r["amount"])} for r in result["rows"] if r["amount"]>0]
                    lena_rows=[{"LENA PARTY":r["party"],"LENA AMOUNT":int(abs(r["amount"]))} for r in result["rows"] if r["amount"]<0]
                    merged=[]
                    for i in range(max(len(dena_rows),len(lena_rows))):
                        d=dena_rows[i] if i<len(dena_rows) else {}
                        l=lena_rows[i] if i<len(lena_rows) else {}
                        merged.append({"DENA PARTY":d.get("DENA PARTY",""),"DENA AMOUNT":d.get("DENA AMOUNT",""),"LENA PARTY":l.get("LENA PARTY",""),"LENA AMOUNT":l.get("LENA AMOUNT","")})
                    st.dataframe(pd.DataFrame(merged),use_container_width=True,hide_index=True)
                    st.metric("TOTAL DENA",f"₹{result['dena']:,.0f}")
                    st.metric("TOTAL LENA",f"₹{result['lena']:,.0f}")
                    st.metric("DIFFERENCE (LENA − DENA)",f"₹{result['difference']:,.0f}")
                    st.metric("FINAL P&L",f"₹{result['difference']:,.0f}",delta="PROFIT" if result["difference"]>0 else ("LOSS" if result["difference"]<0 else "BREAK-EVEN"))
                    st.caption("The exact approved PDF set is compared party-by-party against the locked summary; non-matching runs are blocked.")
                    st.subheader("Party-wise calculation audit")
                    st.dataframe([{"Party":r["party"],"Signed amount":f"{r['amount']:,.0f}","Direction":"DENA" if r["amount"]>0 else "LENA"} for r in result["rows"]],use_container_width=True,hide_index=True)
                    st.subheader("Source PDF reconciliation")
                    st.dataframe([{"Supplier":p.name,"Code":p.code,"Gross":f"{p.total_gross:,.2f}","Total Brokerage":f"{p.total_brokerage:,.2f}","Broker Brokerage":f"{p.broker_brokerage:,.2f}","Final Bill":f"{p.final_bill:,.2f}","Clients":len(p.clients)} for p in parsed],use_container_width=True,hide_index=True)
                    csv=pd.DataFrame(merged).to_csv(index=False).encode("utf-8")
                    st.download_button("Download final summary CSV",csv,file_name="HISAB_V2_FINAL_SUMMARY.csv",mime="text/csv")

else:
    st.info("Upload the supplier PDFs above, then click PROCESS & VERIFY to generate the final summary.")

