# HISAB Version 2.0

Separate V2 repository. This does not modify the existing `bill-summary` repository or Version 1.0 deployment.

Files: `streamlit_app.py`, `requirements.txt`, `saved_rules.json`.

In Streamlit → Advanced settings → Secrets, add:
```toml
GITHUB_TOKEN = "YOUR_FINE_GRAINED_TOKEN"
```
Token access should be limited to this repository with `Contents: Read and write`. Never share it in chat or commit it to the repository.

**Important:** This build includes rule entry and storage setup. Final merged settlement calculation is not implemented or validated against real PDFs yet; do not rely on it as a final financial calculator.
