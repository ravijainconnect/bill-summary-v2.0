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
    "217244", "680260", "914893", "320560", "887584",
}
KNOWN_CLIENT_PATTERNS = {
    "SONU MAK": ["SONI_SC_10L", "DILIP_SC_10L", "BAHETI_SC50L", "SP_MM", "SS12", "SUNIL_SC_10L"],
    "SONU SN": ["PRAHAL_SC_10L", "NISHIDHA_SC_5L", "GANESH_SC_5L", "VIMAL_SC5L"],
    "VIKRAM": ["PANKAJ", "VIPIN"],
    "PATNI": ["GOPAL_", "HIMANSHU_"],
    "RITESH": ["RISHI", "GULLU", "DHEERAJ", "_NB"],
    "SUMIT": ["NITESH_SC4L"],
    "LV": ["LV_"],
    "TONY": ["TONY"],
    "MAHAVIR": ["MAHAVIR"],
    "SPECIAL": ["AM_AA01", "AM_VISHAL"],
}
def known_client_group(client_name):
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
new_clients = [c for c in pdf_client_headers if c["code"] not in MASTER_CLIENT_CODES and known_client_group(c["name"]) is None and c["name"].strip().casefold() not in known_clients]
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
st.warning("Final merged calculation is NOT implemented/validated in this build. Validate PDF extraction and existing Module 1–4 / Merge rules before relying on any final financial result.")
