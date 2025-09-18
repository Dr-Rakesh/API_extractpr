import os
import re
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

import pandas as pd
import requests
from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# --- Configuration ---
BASE_URL = os.getenv("API_BASE_URL", "https://app-adt-11.azurewebsites.net")
TOKEN_PATH = os.getenv("API_TOKEN_PATH", "/auth/token")
MESSAGE_PATH = os.getenv("API_MESSAGE_PATH", "/message")

USERNAME = os.getenv("API_USERNAME", "mahendar.bhandari.ext@siemens.com")
PASSWORD = os.getenv("API_PASSWORD", "12345")
CLIENT_ID = os.getenv("API_CLIENT_ID", "Bearer")

DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("app.log", mode="a")]
)
logger = logging.getLogger(__name__)

def dbg(*args):
    if DEBUG:
        logger.info(" ".join(str(a) for a in args))

# --- App init ---
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

os.makedirs("messages", exist_ok=True)
os.makedirs("output", exist_ok=True)

# --- Helper functions for token & message calls (kept generic) ---
def post_form_token(payload: Dict[str, Any]) -> requests.Response:
    url = BASE_URL + TOKEN_PATH
    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    dbg("Posting form token to", url, "payload keys:", list(payload.keys()))
    return requests.post(url, data=payload, headers=headers, timeout=15)

def post_json_token(payload: Dict[str, Any]) -> requests.Response:
    url = BASE_URL + TOKEN_PATH
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    dbg("Posting json token to", url, "payload keys:", list(payload.keys()))
    return requests.post(url, json=payload, headers=headers, timeout=15)

def extract_token_from_response(resp: requests.Response) -> Optional[Tuple[str, Dict]]:
    try:
        data = resp.json()
    except ValueError:
        dbg("Token response not JSON:", resp.text[:300])
        return None

    for key in ("access_token", "token", "accessToken", "jwt"):
        if key in data and isinstance(data[key], str) and data[key].strip():
            return data[key], data

    # try to find jwt-like string inside nested JSON
    def find_jwt(obj):
        if isinstance(obj, str) and obj.count(".") == 2:
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = find_jwt(v)
                if r:
                    return r
        if isinstance(obj, list):
            for v in obj:
                r = find_jwt(v)
                if r:
                    return r
        return None

    found = find_jwt(data)
    if found:
        return found, data

    dbg("No token key found. Token response (truncated):", json.dumps(data)[:800])
    return None

def obtain_token() -> Tuple[str, Dict]:
    form_candidates = [
        {"grant_type": "password", "username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID},
        {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID},
        {"username": USERNAME, "password": PASSWORD},
    ]
    for p in form_candidates:
        r = post_form_token(p)
        dbg("Token form status:", r.status_code)
        if r.status_code in (200, 201):
            ext = extract_token_from_response(r)
            if ext:
                dbg("Token obtained via form payload")
                return ext

    json_wrappers = ["", "data", "user", "auth", "credentials"]
    for w in json_wrappers:
        payload = ({w: {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID}} if w
                   else {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID})
        r = post_json_token(payload)
        dbg("Token json status:", r.status_code)
        if r.status_code in (200, 201):
            ext = extract_token_from_response(r)
            if ext:
                dbg("Token obtained via json payload")
                return ext

    raise RuntimeError("Failed to obtain token; check token endpoint and credentials.")

def post_message_with_token(token: str, message: str, product: str, version: str, app_id: int, session_id: Optional[str] = None) -> requests.Response:
    url = BASE_URL + MESSAGE_PATH
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    form_data = {"message": message, "product": product, "version": str(version), "app_id": str(app_id)}
    if session_id:
        form_data["session_id"] = session_id
    dbg("Posting to /message with app_id", app_id)
    return requests.post(url, data=form_data, headers=headers, timeout=30)

def save_message_to_file(response_json, question, product, version, app_id):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized = "".join(c if c.isalnum() else "_" for c in question)[:40]
    filename = f"{sanitized}_{ts}.json"
    path = os.path.join("messages", filename)
    wrapper = {
        "question": question,
        "product": product,
        "version": version,
        "app_id": app_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "response": response_json
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(wrapper, fh, indent=2, ensure_ascii=False)
    dbg("Saved message", path)
    return path

def extract_urls_from_response(response_text: str) -> list:
    if not isinstance(response_text, str):
        return []
    parts = response_text.split("Relevant URLs:")
    if len(parts) < 2:
        return []
    urls_section = parts[1]
    url_pattern = r'href=[\'"]([^\'"]+)[\'"]'
    urls = re.findall(url_pattern, urls_section)
    return list(dict.fromkeys(urls))

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    try:
        with open("static/index.html", "r", encoding="utf-8") as fh:
            return HTMLResponse(content=fh.read())
    except FileNotFoundError:
        logger.error("Frontend index.html not found.")
        return HTMLResponse(content="<h1>Error: Frontend files not found</h1>", status_code=500)

@app.post("/debug-form/")
async def debug_form_endpoint(request: Request):
    """
    Temporary debugging endpoint: returns exactly what form keys and values (and file names)
    were received. Use this to confirm whether the browser included app_id in the POST.
    """
    form = await request.form()
    # Build a representation of what was received
    received = {}
    for k, v in form.items():
        if hasattr(v, "filename"):
            # file-like UploadFile
            received[k] = {"type": "file", "filename": v.filename, "content_type": getattr(v, "content_type", None)}
        else:
            received[k] = {"type": "field", "value": str(v)}
    logger.info("Debug-form received keys: %s", list(form.keys()))
    return JSONResponse(content={"received": received})

@app.post("/upload-file/")
async def process_file(
    file: UploadFile = File(...),
    product: str = Form(...),
    version: str = Form(...),
    app_id: Optional[str] = Form(None),
):
    """
    Main upload endpoint. Accepts file + form fields product, version, app_id.
    app_id accepted as string here for debugging (we validate/convert below).
    """
    try:
        logger.info("Received upload request: file=%s product=%s version=%s app_id=%s",
                    getattr(file, "filename", None), product, version, app_id)

        # Validate app_id presence
        if app_id is None or str(app_id).strip() == "":
            # return 400 with clear message (instead of 422) so front-end can show readable error
            return JSONResponse(status_code=400, content={"error": "app_id is required in the form data."})

        # Convert app_id to int
        try:
            app_id_int = int(str(app_id).strip())
        except ValueError:
            return JSONResponse(status_code=400, content={"error": "app_id must be an integer."})

        # Persist uploaded file
        input_filepath = os.path.join("output", file.filename)
        with open(input_filepath, "wb") as fh:
            fh.write(file.file.read())
        dbg("Saved uploaded file to", input_filepath)

        # Load into pandas
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(input_filepath)
        elif ext == ".csv":
            df = pd.read_csv(input_filepath)
        else:
            return JSONResponse(status_code=400, content={"error": "Unsupported file format. Use .xlsx/.xls or .csv"})

        if "Question" not in df.columns:
            return JSONResponse(status_code=400, content={"error": "Uploaded file must contain a 'Question' column."})

        # Add/ensure columns
        if "app_id" not in df.columns:
            df["app_id"] = str(app_id_int)

        evaluation_metrics = [
            "Relevance", "Accuracy", "Clarity", "Tone and Politeness", "Completeness",
            "Engagement", "User Satisfaction", "Bias and Ethical", "Cross-Session Continuity",
            "Information Provenance"
        ]
        for col in evaluation_metrics:
            if col not in df.columns:
                df[col] = ""

        if "Extracted Text" not in df.columns:
            df["Extracted Text"] = ""
        if "Extracted URL" not in df.columns:
            df["Extracted URL"] = ""

        # Obtain token
        try:
            token, token_json = obtain_token()
            logger.info("Token obtained")
        except Exception as e:
            logger.exception("Failed to obtain token")
            return JSONResponse(status_code=500, content={"error": f"Failed to obtain token: {str(e)}"})

        # Process rows and call /message
        total = len(df)
        for idx, row in df.iterrows():
            question = row.get("Question", "")
            if pd.isna(question) or str(question).strip() == "":
                dbg("Skipping empty question at row", idx)
                continue

            # Use per-row app_id if present
            row_app_id_raw = row.get("app_id", app_id_int)
            try:
                row_app_id_int = int(str(row_app_id_raw))
            except Exception:
                row_app_id_int = app_id_int

            q_text = str(question).strip()
            dbg(f"Processing row {idx+1}/{total}: app_id={row_app_id_int} question={q_text[:80]}")

            try:
                resp = post_message_with_token(token=token, message=q_text, product=product, version=version, app_id=row_app_id_int)
            except requests.RequestException as e:
                logger.error("Request exception for row %s: %s", idx+1, e)
                df.at[idx, "Extracted Text"] = "Error: API request failed"
                df.at[idx, "Extracted URL"] = "No URL found"
                continue

            if resp.status_code == 200:
                try:
                    resp_json = resp.json()
                except ValueError:
                    resp_json = {"message": resp.text}
                resp_text = resp_json.get("message", "") if isinstance(resp_json, dict) else str(resp_json)
                urls = extract_urls_from_response(resp_text)

                df.at[idx, "Extracted Text"] = resp_text
                df.at[idx, "Extracted URL"] = "\n".join(urls) if urls else "No URL found"
                save_message_to_file(resp_json, q_text, product, version, row_app_id_int)
            else:
                logger.warning("Non-200 from /message for row %s: %s - %s", idx+1, resp.status_code, (resp.text or "")[:300])
                df.at[idx, "Extracted Text"] = f"Error: API returned {resp.status_code}"
                df.at[idx, "Extracted URL"] = "No URL found"

        # Save processed DataFrame to file and return
        out_name = f"processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        out_path = os.path.join("output", out_name)
        if ext in (".xlsx", ".xls"):
            df.to_excel(out_path, index=False)
        else:
            df.to_csv(out_path, index=False)

        dbg("Saved processed file:", out_path)
        return FileResponse(out_path, filename=out_name)

    except Exception as ex:
        logger.exception("Unhandled error in /upload-file/")
        return JSONResponse(status_code=500, content={"error": str(ex)})