import requests
import json
import sys

BASE_URL = "https://app-adt-11.azurewebsites.net"
TOKEN_PATH = "/auth/token"
USERNAME = "mahendar.bhandari.ext@siemens.com"
PASSWORD = "12345"
CLIENT_ID = "Bearer"

def try_json(payload):
    url = BASE_URL + TOKEN_PATH
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    print("\nPOST JSON to", url)
    print("Headers:", headers)
    print("JSON body:", json.dumps(payload, indent=2))
    r = requests.post(url, json=payload, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Response:", r.text)
    return r

def try_form(payload):
    url = BASE_URL + TOKEN_PATH
    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    print("\nPOST form to", url)
    print("Headers:", headers)
    print("Form data:", payload)
    r = requests.post(url, data=payload, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Response:", r.text)
    return r

def main():
    # 1) Try application/x-www-form-urlencoded (OAuth2 style)
    form_payload = {
        "grant_type": "password",
        "username": USERNAME,
        "password": PASSWORD,
        "client_id": CLIENT_ID
    }
    r = try_form(form_payload)
    if r.status_code in (200, 201):
        print("Success with form-encoded payload.")
        print(r.json())
        return

    # 2) Try raw JSON (we already tried many shapes earlier; try wrapper keys)
    wrappers = ["", "data", "user", "auth", "credentials"]
    for w in wrappers:
        if w:
            payload = {w: {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID}}
        else:
            payload = {"username": USERNAME, "password": PASSWORD, "client_id": CLIENT_ID}
        r = try_json(payload)
        if r.status_code in (200, 201):
            print("Success with JSON payload:", payload)
            print(r.json())
            return

    # 3) Try JSON but with fields as lists (unlikely) or null-check variants if needed
    print("\nAll attempts failed. If you can open the Swagger UI and paste the Request body schema for POST /auth/token (the example JSON shown when you expand the endpoint), I will tailor the exact request shape.")
    print("Also check the endpoint's 'Consumes' media type in the OpenAPI docs — if it lists application/x-www-form-urlencoded, use form encoding.")

if __name__ == "__main__":
    main()