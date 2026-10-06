# Clé as LLM for BayesPlatform (test setup, 6 October 2026)

Clé (`https://cle.charite.de/api`, OpenAI-compatible, model `eu` = Mistral Small 4) was connected to BayesPlatform on 6 October 2026 for a test. It worked for plain chat but **not with MCP tools**: Clé's API returns an empty message (`content: ""`, `tool_calls: null`, or a stream with `choices: []`) for every request that includes `tools`. Tested with `eu`, `mistralai/Mistral-Small-4-119B-2603`, `fast` and `frontier`. The Clé team was asked to enable tool calling (likely vLLM `--enable-auto-tool-choice --tool-call-parser mistral`) and access from the de.NBI network.

## Why it needed a tunnel

Clé is only reachable inside the Charité network. From the de.NBI cluster every request times out, so the path was:

```
BayesPlatform API --(Mistral slot)--> cle-gateway --TLS--> cle-relay:443 (pod 8443)
   ==ssh -R through kubectl port-forward==> Elias's Mac (Charité network) --> cle.charite.de:443
```

Nothing is opened on the shared jumphost, and TLS terminates at Clé itself (the gateway pod resolves `cle.charite.de` to the relay Service via `hostAliases`). The tunnel only works while the Mac is awake and the ssh command runs.

## Pieces

- `cle-relay.yaml`: alpine + sshd. User `tunnel`, public-key only (`~/.ssh/bayes_cle_relay` on the Mac; the ConfigMap `cle-relay-key` holds only the `.pub`), remote forwarding to `0.0.0.0:8443` only (unprivileged user cannot bind 443). Service port 443 → pod 8443.
- `cle-gateway.yaml`: small Node server.
  - Answers the GCE metadata token request with a dummy token: BayesPlatform's OpenAI-compatible Mistral provider always fetches a Google token, so `GCE_METADATA_HOST` and `METADATA_SERVER_DETECTION=assume-present` point it here.
  - Forwards `/v1/*` to `CLE_BASE_URL` with the Clé key and rewrites `model` to `CLE_MODEL` (header `x-cle-model` overrides it for tests).
- `values.yaml` (`config:`): `VLLM_MISTRALSMALL31_24B_URL=http://cle-gateway…:8080/v1`, `VLLM_MISTRALSMALL31_24B_APIKEY=unused`, `GCE_METADATA_HOST`, `METADATA_SERVER_DETECTION`. In the workspace, the back-office feature flags `mistral` and `agent-mcp` must be on.

## Bring it back

```sh
# token, never in the repo
read -rs "CLE_TOKEN?Clé token: "; echo
kubectl -n bayes-platform create secret generic cle-api --from-literal=CLE_API_KEY="$CLE_TOKEN"; unset CLE_TOKEN
kubectl -n bayes-platform create configmap cle-relay-key --from-file=authorized_keys=$HOME/.ssh/bayes_cle_relay.pub
kubectl apply -f cle-relay.yaml -f cle-gateway.yaml   # check the relay ClusterIP in cle-gateway hostAliases
# helm upgrade with values.yaml pointing the Mistral slot at cle-gateway (see README)

# on the Mac, keep open:
kubectl -n bayes-platform port-forward svc/cle-relay 2222:22 &
ssh -N -i ~/.ssh/bayes_cle_relay -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -R 0.0.0.0:8443:cle.charite.de:443 tunnel@127.0.0.1
```
