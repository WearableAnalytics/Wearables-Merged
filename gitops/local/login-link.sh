#!/usr/bin/env bash
set -euo pipefail

# Prints a one-use login link for the local web frontend, valid for 60 seconds.
#
# In development mode the BFF sends no mail, and its email-only login
# (ALLOW_DEV_AUTH_BYPASS) only works on loopback addresses, not behind Traefik.
# Like deploy/local/login_link.py for Docker Compose, this asks db_lord for a
# login challenge directly. It runs inside the db_lord pod, which has the
# CONTROL_WRITE_TOKEN, so the token never leaves the cluster.

CONTEXT="minikube"
EMAIL="${1:-admin@example.com}"
BASE_URL="${BASE_URL:-http://wearables.localhost}"

case "$EMAIL" in
  -h|--help)
    echo "Usage: ./gitops/local/login-link.sh [email]   (default: admin@example.com)"
    exit 0 ;;
esac

kubectl --context "$CONTEXT" exec -i -n db-lord deploy/db-lord -- \
  python - "$EMAIL" "$BASE_URL" <<'PY'
import hashlib, json, os, secrets, sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

email, base_url = sys.argv[1].strip().lower(), sys.argv[2].rstrip("/")

def request(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = Request("http://127.0.0.1:8000/control" + path, data=data, headers={
        "X-Control-Service-Token": os.environ["CONTROL_WRITE_TOKEN"],
        "Content-Type": "application/json",
    })
    try:
        with urlopen(req, timeout=10) as response:
            return json.load(response)
    except HTTPError as error:
        sys.exit(f"db_lord answered {error.code} for {path}: {error.read().decode()}")

items = request("/users?" + urlencode({"email": email}))["items"]
if len(items) != 1:
    sys.exit(f"No account for {email}. Admins (ADMIN_EMAILS of wearables-bff) are created when the BFF "
             "starts; other users have to register and be approved first.")
account = items[0]
if account["status"] != "approved":
    sys.exit(f"{email} is {account['status']}; an admin has to approve it first.")

proof = secrets.token_hex(32)
request("/login-challenges", {
    "token_hash": hashlib.sha256(proof.encode()).hexdigest(),
    "user_id": account["id"],
    "auth_version": account["auth_version"],
    "ttl_seconds": 60,
})
print(f"{base_url}/api/verify-magiclink?{urlencode({'token': proof})}")
PY
