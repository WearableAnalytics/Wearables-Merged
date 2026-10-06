# Bayes prototype

Runs the Bayes prototype ([bayesimpact/charite](https://github.com/bayesimpact/charite), private) in its own `bayes-prototype` namespace next to the wearables platform.

The prototype repo is private, so there is no image on a public registry. `deploy.sh` copies a `git archive` of a local clone onto a PVC, builds it in the cluster with `node:24-slim`, and then the Deployment runs from that volume.

```sh
BAYES_REPO=~/Desktop/charite ./deploy.sh          # BAYES_REF defaults to main
```

The cluster API is only reachable from the de.NBI network. From a laptop, open a SOCKS tunnel through the jumphost first:

```sh
ssh -N -D 127.0.0.1:18080 denbi-jumphost-01.bihealth.org &
export HTTPS_PROXY=socks5://127.0.0.1:18080
```

## What runs

| Container | Port | Notes |
| --- | --- | --- |
| `web` | 4173 (`svc/bayes-prototype:80`) | `vite preview` of the fake dotbase and assistant shell |
| `mcp-server` | 127.0.0.1:3333 | MCP server; binds loopback only |
| `mcp-proxy` | 8080 (`svc/bayes-prototype:3333`) | socat, exposes the MCP server on the pod IP |

The Service is ClusterIP only. Open it locally with:

```sh
kubectl -n bayes-prototype port-forward svc/bayes-prototype 8081:80 3333:3333
# UI:  http://127.0.0.1:8081/dotbase
# MCP: http://127.0.0.1:3333/mcp
```

## InfluxDB token

The MCP server reads the in-cluster InfluxDB (`wearables-project` / `measurements`, the same as Telegraf). Its token comes from the optional `bayes-influx` Secret: a read-only token for the `measurements` bucket. Create it with an Influx admin token, without printing either:

```sh
P=$(kubectl -n influx get pod -o name | head -1)
printf '%s\n' "$INFLUX_ADMIN_TOKEN" | kubectl -n influx exec -i "$P" -- sh -c '
  read -r T; export INFLUX_TOKEN="$T"
  B=$(influx bucket list --org wearables-project --name measurements --hide-headers | cut -f1)
  influx auth create --org wearables-project --read-bucket "$B" --description bayes-prototype-read --json' \
  | jq -r .token | kubectl -n bayes-prototype create secret generic bayes-influx --from-file=INFLUX_TOKEN=/dev/stdin
kubectl -n bayes-prototype rollout restart deploy/bayes-prototype
```

## Not wired up yet

- Patients come from the prototype's fake SQLite DB, not from db-lord.
- No `VITE_BAYES_EMBED_*`, so the assistant chat panel shows its configuration message.
- No public route on `wearables.charite.de`.
