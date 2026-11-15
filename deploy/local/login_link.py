"""Issue a one-use local login link through the protected account authority."""

import argparse
import hashlib
import json
from pathlib import Path
import secrets
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from init_env import read_env


def loopback_url(value):
    url = urlsplit(value)
    if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
            or url.username or url.password or url.query or url.fragment):
        raise ValueError("This helper accepts only HTTP loopback development endpoints")
    return value.rstrip("/")


def login_link(values, email, database_url, bff_url):
    database_url, bff_url = loopback_url(database_url), loopback_url(bff_url)
    credential = values["CONTROL_WRITE_TOKEN"]

    def request(path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = Request(database_url + path, data=data, headers={
            "X-Control-Service-Token": credential, "Content-Type": "application/json",
        })
        with urlopen(req, timeout=10) as response:
            return json.load(response)

    page = request("/control/users?" + urlencode({"email": email.strip().lower()}))
    if len(page["items"]) != 1 or page.get("next_cursor"):
        raise ValueError("No unique account found; start the BFF and complete registration/approval first")
    account = page["items"][0]
    if account["status"] != "approved":
        raise ValueError("An administrator must approve this account first")
    proof = secrets.token_hex(32)
    request("/control/login-challenges", {
        "token_hash": hashlib.sha256(proof.encode()).hexdigest(), "user_id": account["id"],
        "auth_version": account["auth_version"], "ttl_seconds": 60,
    })
    return bff_url + "/verify-magiclink?" + urlencode({"token": proof})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env"))
    parser.add_argument("--email")
    parser.add_argument("--database-url", default="http://127.0.0.1:8000")
    parser.add_argument("--bff-url", default="http://localhost:3001/api")
    args = parser.parse_args()
    values = read_env(args.env_file)
    email = args.email or values["ADMIN_EMAILS"].split(",")[0]
    print(login_link(values, email, args.database_url, args.bff_url))
