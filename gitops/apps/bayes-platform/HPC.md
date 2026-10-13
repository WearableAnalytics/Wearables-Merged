# HPC-hosted model for BayesPlatform (test setup, October 2026)

For testing, BayesPlatform's model slot can use an open-weight model served with vLLM in a GPU job on the Charité HPC. Long term the plan is Clé (`CLE.md`); the default stays the local Ollama model (`llm-gateway.yaml`).

Tested on 13 October 2026 with `gpt-oss-120b` (vLLM 0.11, two GPUs, tensor parallel 2): tool calls, tool-result round trip, streaming and the wearables MCP tools all worked, including patient questions that Clé refuses.

## Path

```
BayesPlatform API --> llm-gateway --> llm-relay:8443 ==ssh -R==> Mac ==ssh -L==> GPU node 127.0.0.1:8000 (vLLM)
```

vLLM listens only on the GPU node's localhost, so other HPC users cannot reach it; the Mac reaches it through the HPC login node. The tunnels only work while the Mac is awake.

## Pieces

- GPU job: a venv with `vllm==0.11.0` and `transformers<4.58` (the HPC GPU driver supports CUDA 12 only; newer vLLM wheels need CUDA 13). Job command:

  ```sh
  vllm serve <model dir> --served-model-name gpt-oss-120b --host 127.0.0.1 --port 8000 \
    --enable-auto-tool-choice --tool-call-parser openai --reasoning-parser openai_gptoss \
    --tensor-parallel-size 2 --max-model-len 65536
  ```

  A one-GPU request on the multi-GPU partition gets moved to the single-GPU partition and may queue; two GPUs started immediately.
- `llm-relay.yaml`: sshd pod for the reverse tunnel (public key only).
- `llm-gateway` ConfigMap: `UPSTREAM_BASE_URL=http://llm-relay.bayes-platform.svc.cluster.local:8443/v1`, `UPSTREAM_MODEL=gpt-oss-120b`.

## Switch

```sh
# to the HPC model (after the tunnels in llm-relay.yaml are up)
kubectl -n bayes-platform patch configmap llm-gateway --type merge -p \
  '{"data":{"UPSTREAM_BASE_URL":"http://llm-relay.bayes-platform.svc.cluster.local:8443/v1","UPSTREAM_MODEL":"gpt-oss-120b"}}'
# back to Ollama
kubectl -n bayes-platform patch configmap llm-gateway --type merge -p \
  '{"data":{"UPSTREAM_BASE_URL":"http://ollama.bayes-llm.svc.cluster.local:11434/v1","UPSTREAM_MODEL":"gemma4:26b-a4b"}}'
kubectl -n bayes-platform rollout restart deploy/llm-gateway
```
