import io, json, re, base64
from datetime import datetime, timezone
import requests
import streamlit as st
import pdfplumber

st.set_page_config(page_title="HISAB Version 2.0", page_icon="📊", layout="wide")
OWNER, REPO, BRANCH, RULES_PATH = "ravijainconnect", "hisab-v2", "main", "saved_rules.json"

st.title("📊 HISAB — Version 2.0")
st.caption("Separate V2 app. The existing Version 1.0 repository/deployment is not modified.")

def gh_headers():
    token = st.secrets.get("GITHUB_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"} if token else None

def load_rules():
    h = gh_headers()
    if not h: return [], None, "Persistent saving is not configured. Add GITHUB_TOKEN to Streamlit Secrets."
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{RULES_PATH}?ref={BRANCH}"
    try:
        r = requests.get(url, headers=h, timeout=15)
        if r.status_code == 404: return [], None, None
        r.raise_for_status()
        p = r.json()
        return json.loads(base64.b64decode(p["content"]).decode()), p["sha"], None
    except Exception as e: return [], None, f"Could not load saved rules: {e}"

def save_rules(rules, sha):
    h = gh_headers()
    if not h: return False, "Add GITHUB_TOKEN in Streamlit Secrets to enable permanent saving."
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/{RULES_PATH}"
    body = {"message":"Save HISAB V2 client rule",
            "content":base64.b64encode(json.dumps(rules, ensure_ascii=False, indent=2).encode()).decode(),
            "branch":BRANCH}
    if sha: body["sha"] = sha
    try:
        r = requests.put(url, headers=h, json=body, timeout=20)
        r.raise_for_status()
        return True, "Rule saved to the HISAB V2 repository."
    except Exception as e: return False, f"Save failed: {e}"

files = st.file_uploader("1. Upload settlement PDFs", type=["pdf"], accept_multiple_files=True)
names = []
if files:
    for f in files:
        try:
            with pdfplumber.open(io.BytesIO(f.getvalue())) as pdf:
                text = "\n".join(p.extract_text(x_tolerance=2, y_tolerance=3) or "" for p in pdf.pages)
            match = re.search(r"\((\d{5,})\)\s*([^\n]+)", text)
            if match:
                n = match.group(2).strip()
                if n and n not in names: names.append(n)
        except Exception: pass
    st.caption(f"PDF files selected: {len(files)}")
    st.write("Names detected (review before saving):" if names else "No names detected; PDF format needs validation.")
    if names: st.write(", ".join(names))

rules, sha, error = load_rules()
if error: st.warning(error)
else: st.success(f"Saved rules loaded: {len(rules)}")

known_clients = {str(x.get("detected_client", "")).strip().casefold() for x in rules if x.get("detected_client")}
new_clients = [n for n in names if n.strip().casefold() not in known_clients]
if new_clients:
    st.subheader("New Client Module")
    client = new_clients[0]
    st.text_input("1. FOUND NEW CLIENT (auto-detected / locked)", value=client or "Waiting for PDF detection", disabled=True)
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
        elif not client: st.error("Upload a PDF and ensure a client name is detected.")
        else:
            new = {"detected_client":client,"first_person":first,"first_sharing_pct":share1,"first_basis":basis1,
                   "first_broker_brokerage_sharing_pct":broker1,"first_total_brokerage_sharing_pct":total1,
                   "has_second_person":second,"second_basis":basis2,"second_sharing_pct":share2,
                   "second_broker_brokerage_sharing_pct":broker2,"second_total_brokerage_sharing_pct":total2,
                   "rule_type":kind,"saved_at_utc":datetime.now(timezone.utc).isoformat()}
            rules.append(new)
            ok, msg = save_rules(rules, sha)
            if ok: st.success(msg); st.rerun()
            else: rules.pop(); st.error(msg)


st.subheader("Saved Rules")
if rules:
    st.dataframe(rules, use_container_width=True, hide_index=True)
    st.download_button("Download saved rules backup", json.dumps(rules, ensure_ascii=False, indent=2),
                       file_name="hisab_v2_saved_rules_backup.json", mime="application/json")
else: st.info("No rules saved yet.")

st.subheader("Settlement Summary")
st.warning("Final merged calculation is NOT implemented/validated in this build. Validate PDF extraction and existing Module 1–4 / Merge rules before relying on any final financial result.")
