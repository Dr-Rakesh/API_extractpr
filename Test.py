#!/usr/bin/env python3
"""
Combined script:
1) Obtain token from POST /auth/token
2) Use token to POST /message (application/x-www-form-urlencoded)

Usage: update USERNAME, PASSWORD (or set env vars), then run.
"""

import os
import json
import requests
import sys
from typing import Optional, Tuple, Dict, Any

BASE_URL = "https://app-adt-11.azurewebsites.net"
TOKEN_PATH = "/auth/token"
MESSAGE_PATH = "/message"

# Credentials - for safety you can set these as environment variables instead of hard-coding
USERNAME = os.getenv("API_USERNAME", "mahendar.bhandari.ext@siemens.com")
PASSWORD = os.getenv("API_PASSWORD", "12345")
CLIENT_ID = os.getenv("API_CLIENT_ID", "Bearer")  # per your earlier message

# Optional: set to True to print lots of debug info
DEBUG = True

def dbg(*args, **kwargs):
    if DEBUG:
        print(*args, **kwargs)

def post_form_token(payload: Dict[str, Any]) -> requests.Response:
    url = BASE_URL + TOKEN_PATH
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    dbg("\nPOST (form) to", url)
    dbg("Headers:", headers)
    dbg("Form data:", payload)
    return requests.post(url, data=payload, headers=headers, timeout=15)

def post_json_token(payload: Dict[str, Any]) -> requests.Response:
    url = BASE_URL + TOKEN_PATH
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    dbg("\nPOST (json) to", url)
    dbg("Headers:", headers)
    dbg("JSON body:", json.dumps(payload, indent=2))
    return requests.post(url, json=payload, headers=headers, timeout=15)

def extract_token_from_response(resp: requests.Response) -> Optional[Tuple[str, Dict]]:
    """
    Try to extract token from common keys in JSON response.
    Returns (token, full_json) or None
    """
    try:
        data = resp.json()
    except ValueError:
        dbg("Token endpoint did not return JSON:", resp.text)
        return None

    # Common keys
    for key in ("access_token", "token", "accessToken", "jwt"):
        if key in data and isinstance(data[key], str) and data[key].strip():
            return data[key], data

    # Some APIs return nested structures; attempt to find the first string value that looks like a JWT (3 parts separated by .)
    def find_jwt_like(obj):
        if isinstance(obj, str):
            parts = obj.split(".")
            if len(parts) == 3:
                return obj
        if isinstance(obj, dict):
            for v in obj.values():
                found = find_jwt_like(v)
                if found:
                    return found
        if isinstance(obj, list):
            for v in obj:
                found = find_jwt_like(v)
                if found:
                    return found
        return None

    found = find_jwt_like(data)
    if found:
        return found, data

    dbg("Could not find token key in JSON response. Full JSON:")
    dbg(json.dumps(data, indent=2))
    return None

def obtain_token() -> Tuple[str, Dict]:
    """Try multiple request shapes to obtain an auth token."""
    # 1) Try form-encoded OAuth2 password grant (very common)
    form_payloads = [
        {"grant_type": "password", "username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID},
        {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID},
        {"username": USERNAME, "password": PASSWORD}
    ]
    for p in form_payloads:
        r = post_form_token(p)
        dbg("Status:", r.status_code)
        dbg("Response:", r.text)
        if r.status_code in (200, 201):
            extracted = extract_token_from_response(r)
            if extracted:
                dbg("Token extracted using form payload:", p)
                return extracted
        else:
            dbg("Form attempt failed with status", r.status_code)

    # 2) Try JSON payloads (some FastAPI endpoints expect JSON body)
    json_wrappers = ["", "data", "user", "auth", "credentials"]
    for w in json_wrappers:
        if w:
            payload = {w: {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID}}
        else:
            payload = {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID}
        r = post_json_token(payload)
        dbg("Status:", r.status_code)
        dbg("Response:", r.text)
        if r.status_code in (200, 201):
            extracted = extract_token_from_response(r)
            if extracted:
                dbg("Token extracted using json payload wrapper:", w or "<none>")
                return extracted
        else:
            dbg("JSON attempt failed with status", r.status_code)

    # 3) If still not found, raise with debugging hint
    raise RuntimeError(
        "Failed to obtain token. Server responses printed above. "
        "Check the POST /auth/token schema in Swagger (openapi.json) and adapt payload accordingly."
    )

def post_message_with_token(token: str, message: str, product: str, version: str, app_id: int, session_id: Optional[str]=None) -> requests.Response:
    url = BASE_URL + MESSAGE_PATH
    headers = {
        "Accept": "application/json",
        # use Authorization header (Bearer scheme) which is typical
        "Authorization": f"Bearer {token}",
        # requests will set Content-Type for form data automatically when using data=...
    }
    form_data = {
        "message": message,
        "product": product,
        "version": str(version),
        "app_id": str(app_id)
    }
    if session_id is not None:
        form_data["session_id"] = session_id

    dbg("\nPOST /message to", url)
    dbg("Headers:", headers)
    dbg("Form data:", form_data)
    return requests.post(url, data=form_data, headers=headers, timeout=150)

def main():
    try:
        dbg("Attempting to obtain token from", BASE_URL + TOKEN_PATH)
        token, token_json = obtain_token()
        print("Token obtained:", token)
        dbg("Full token response JSON:", json.dumps(token_json, indent=2))

        # Prepare message payload (per your request)
        message = "What is BOM in team center?"
        product = "Teamcenter"
        version = "2506"
        app_id = 1
        session_id = None  # optional

        resp = post_message_with_token(token, message, product, version, app_id, session_id)
        dbg("Message endpoint status:", resp.status_code)
        dbg("Message endpoint response text:", resp.text)

        # Try parse JSON
        try:
            out = resp.json()
            print("\n/message response (JSON):")
            print(json.dumps(out, indent=2))
        except ValueError:
            print("\n/message response (raw):")
            print(resp.text)

    except requests.HTTPError as he:
        print("HTTP error:", he, file=sys.stderr)
        if he.response is not None:
            print("Status:", he.response.status_code, file=sys.stderr)
            print("Body:", he.response.text, file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print("Error:", str(e), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()