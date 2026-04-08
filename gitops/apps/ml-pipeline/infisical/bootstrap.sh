#!/bin/bash
set -e

# =============================================================================
# Infisical Bootstrap — seeds all ML pipeline secrets into Infisical
# =============================================================================
# Prerequisites:
#   - INFISICAL_TOKEN env var must be set (machine-identity token)
#   - One of: infisical CLI, python3, or curl (tried in that order)
#
# Usage:
#   ./infisical/bootstrap.sh
#   ./infisical/bootstrap.sh --env prod           # override environment (default: prod)
#   ./infisical/bootstrap.sh --project <id>       # override project ID
#   ./infisical/bootstrap.sh --host https://...   # override Infisical host (default: cloud)
#   ./infisical/bootstrap.sh --dry-run            # print without writing
#   ./infisical/bootstrap.sh --file infisical/bootstrap/secrets.env  # override file
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ENV_SLUG="prod"
PROJECT_SLUG="ml-pipeline"  # slug used by the API; CLI path needs --projectId <UUID> — update if using CLI
SECRETS_FILE="$SCRIPT_DIR/bootstrap/secrets.env"
# first forward with  kubectl port-forward svc/infisical-infisical-standalone-infisical -n infisical 8081:8080
INFISICAL_HOST="${INFISICAL_HOST:-http://localhost:8081}"
DRY_RUN=false

# ── argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case $1 in
        --env)       ENV_SLUG="$2";       shift 2 ;;
        --project)   PROJECT_SLUG="$2";   shift 2 ;;
        --host)      INFISICAL_HOST="$2"; shift 2 ;;
        --file)      SECRETS_FILE="$2";   shift 2 ;;
        --dry-run)   DRY_RUN=true;        shift ;;
        -h|--help)
            sed -n '/^# ====/,/^# ====/p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── secrets file check ────────────────────────────────────────────────────────
if [ ! -f "$SECRETS_FILE" ]; then
    echo "ERROR: secrets file not found: $SECRETS_FILE"
    echo ""
    echo "Create it by copying the example:"
    echo "  cp infisical/bootstrap/secrets.env.example infisical/bootstrap/secrets.env"
    echo "Then edit the values as needed and re-run."
    exit 1
fi

# ── detect push method ────────────────────────────────────────────────────────
if command -v infisical &>/dev/null; then
    PUSH_METHOD="cli"
elif command -v python3 &>/dev/null; then
    PUSH_METHOD="python3"
    if [ -z "${INFISICAL_TOKEN:-}" ]; then
        echo "ERROR: INFISICAL_TOKEN must be exported when using the API (no CLI found)."
        exit 1
    fi
elif command -v curl &>/dev/null; then
    PUSH_METHOD="curl"
    if [ -z "${INFISICAL_TOKEN:-}" ]; then
        echo "ERROR: INFISICAL_TOKEN must be exported when using the API (no CLI found)."
        exit 1
    fi
else
    echo "ERROR: no supported push method found."
    echo "Install one of: infisical CLI, python3, or curl."
    exit 1
fi

echo "Bootstrapping Infisical secrets"
echo "  method  : $PUSH_METHOD"
echo "  project : $PROJECT_SLUG"
echo "  env     : $ENV_SLUG"
echo "  host    : $INFISICAL_HOST"
echo "  file    : $SECRETS_FILE"
[ "$DRY_RUN" = true ] && echo "  mode    : DRY-RUN (no writes)"
echo ""

# ── parse secrets file ────────────────────────────────────────────────────────
declare -a SECRET_KEYS=()
declare -a SECRET_VALUES=()

while IFS= read -r line || [ -n "$line" ]; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    [[ -z "$key" ]] && continue

    if [ "$DRY_RUN" = true ]; then
        echo "  [DRY-RUN] $key=<${#value} chars>"
    else
        SECRET_KEYS+=("$key")
        SECRET_VALUES+=("$value")
    fi
done < "$SECRETS_FILE"

[ "$DRY_RUN" = true ] && { echo ""; echo "Dry-run complete. No secrets were written."; exit 0; }
[ ${#SECRET_KEYS[@]} -eq 0 ] && { echo "No secrets found in $SECRETS_FILE"; exit 0; }

echo "Pushing ${#SECRET_KEYS[@]} secrets to Infisical..."

# ── push via CLI ──────────────────────────────────────────────────────────────
if [ "$PUSH_METHOD" = "cli" ]; then
    set_args=()
    for i in "${!SECRET_KEYS[@]}"; do
        set_args+=("${SECRET_KEYS[$i]}=${SECRET_VALUES[$i]}")
    done
    # NOTE: --projectId expects the project UUID, not the slug.
    # If the CLI is v0.28+ it also accepts --projectSlug.
    # Replace $PROJECT_SLUG with your project's UUID if using this path.
    infisical secrets set \
        --projectId "$PROJECT_SLUG" \
        --env "$ENV_SLUG" \
        "${set_args[@]}"
elif [ "$PUSH_METHOD" = "python3" ]; then
    # Encode secrets to a string to avoid pipe/stdin conflicts
    export BOOTSTRAP_DATA=$(printf '%s\0' "${SECRET_KEYS[@]}" "${SECRET_VALUES[@]}" | base64 | tr -d '\n')
    
    python3 - <<PYEOF
import json, sys, urllib.request, urllib.error, os, base64

# Decode from environment variable instead of stdin
try:
    raw_data = base64.b64decode(os.environ.get('BOOTSTRAP_DATA', ''))
    raw = raw_data.rstrip(b'\x00').split(b'\x00')
    if not raw or raw == [b'']:
        print("ERROR: No secret data reached the Python subshell.")
        sys.exit(1)
        
    n = len(raw) // 2
    keys   = [b.decode() for b in raw[:n]]
    values = [b.decode() for b in raw[n:]]

    secrets = [
        {"secretKey": k, "secretValue": v, "type": "shared"}
        for k, v in zip(keys, values)
    ]

    payload = json.dumps({
        "projectSlug": "$PROJECT_SLUG",
        "environment": "$ENV_SLUG",
        "secretPath": "/",
        "secrets": secrets,
    }).encode()

    req = urllib.request.Request(
        "$INFISICAL_HOST/api/v3/secrets/batch/raw",
        data=payload,
        headers={
            "Authorization": "Bearer $INFISICAL_TOKEN",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    
    with urllib.request.urlopen(req) as resp:
        print(f"  API response {resp.status}: ok ({len(secrets)} secrets upserted)")
        
except urllib.error.HTTPError as e:
    print(f"  ERROR {e.code}: {e.read().decode()}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"  INTERNAL ERROR: {str(e)}", file=sys.stderr)
    sys.exit(1)
PYEOF
    unset BOOTSTRAP_DATA

# ── push via curl (one request per secret — no jq needed) ─────────────────────
elif [ "$PUSH_METHOD" = "curl" ]; then
    # Batch upsert: build JSON manually (values are base64-encoded to dodge quoting)
    # Uses Python-free approach: build raw JSON with printf + sed escaping
    json_secrets=""
    sep=""
    for i in "${!SECRET_KEYS[@]}"; do
        k="${SECRET_KEYS[$i]}"
        # Escape the value: backslash, double-quote, and control chars
        v=$(printf '%s' "${SECRET_VALUES[$i]}" \
            | sed 's/\\/\\\\/g; s/"/\\"/g; s/	/\\t/g')
        json_secrets="${json_secrets}${sep}{\"secretKey\":\"${k}\",\"secretValue\":\"${v}\",\"type\":\"shared\"}"
        sep=","
    done

    payload="{\"projectSlug\":\"${PROJECT_SLUG}\",\"environment\":\"${ENV_SLUG}\",\"secretPath\":\"/\",\"secrets\":[${json_secrets}]}"

    http_code=$(curl -s -o /tmp/_infisical_resp.json -w "%{http_code}" \
        -X POST "${INFISICAL_HOST}/api/v3/secrets/batch/raw" \
        -H "Authorization: Bearer ${INFISICAL_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "$payload")

    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 300 ]; then
        echo "  API response ${http_code}: ok (${#SECRET_KEYS[@]} secrets upserted)"
    else
        echo "ERROR: API returned HTTP ${http_code}:" >&2
        cat /tmp/_infisical_resp.json >&2
        rm -f /tmp/_infisical_resp.json
        exit 1
    fi
    rm -f /tmp/_infisical_resp.json
fi

echo ""
echo "Done. The Infisical operator will sync secrets to Kubernetes within ~60s."
echo "Verify: kubectl get secrets -A | grep -E 'postgres-setup|seaweedfs|lakefs|mlflow|feast|spark-pipeline|kserve'"
