"""Verify actual Helm Starlark output against the committed patient dashboard queries.

Docker creates one disposable local InfluxDB container. No cluster, external
provider or existing database is used. All identifiers and credentials are synthetic.
"""
import json
import os
import shutil
import subprocess
import time
import tomllib
from pathlib import Path
from uuid import uuid4

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
HELM = os.getenv("HELM_BINARY") or shutil.which("helm")
DASHBOARDS = [ROOT / "observability/dashboards" / name for name in
              ("standard-dash-2026-04-11.json", "6mgt-dash-2026-04-11.json")]


def targets(value):
    if isinstance(value, dict):
        if isinstance(value.get("query"), str) and value["query"].startswith("SELECT "):
            yield value
        for child in value.values():
            yield from targets(child)
    elif isinstance(value, list):
        for child in value:
            yield from targets(child)


def test_patient_panels_execute_their_committed_queries():
    for path in DASHBOARDS:
        dashboard = json.loads(path.read_text())
        panels = list(targets(dashboard))
        assert panels
        for panel in panels:
            assert panel["rawQuery"] is True, (path.name, panel["query"])
            assert '"device-id" =~ /^$deviceId$/' in panel["query"]
            assert '"source-key" =~ /^$sourceKey$/' in panel["query"]
            assert 'GROUP BY "source-key"' in panel["query"]
            assert '"source-device-id"' not in panel["query"], "Uploader ID is not patient identity"


@pytest.mark.skipif(os.getenv("GRAFANA_IDENTITY_TEST") != "1" or not HELM,
                    reason="Set GRAFANA_IDENTITY_TEST=1 and install Helm/Docker for the isolated query check")
def test_rendered_telegraf_keeps_new_and_legacy_patients_visible_in_grafana(tmp_path):
    import httpx

    def docker(*arguments):
        result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    endpoint = docker("context", "inspect", "--format", "{{.Endpoints.docker.Host}}")
    assert endpoint.startswith("unix://"), "Refuse a remote Docker engine"
    rendered = subprocess.run([HELM, "template", "identity-test",
        str(ROOT / "gitops/apps/monitoring/telegraf")], check=True, capture_output=True, text=True).stdout
    config = next(d["data"]["telegraf.conf"] for d in yaml.safe_load_all(rendered) if d and d["kind"] == "ConfigMap")
    processor = tomllib.loads(config)["processors"]["starlark"][0]["source"]
    stamp = time.time_ns()
    lines = [
        f'heart-rate,device-id-reference=Patient/participant-a,source-device-id=shared-phone,source-key=source-a value=72 {stamp}',
        f'heart-rate,device-id-reference=Patient/participant-b,source-device-id=shared-phone,source-key=source-a value=99 {stamp}',
        f'heart-rate,device-id=legacy-participant,source-key=source-a value=61 {stamp}',
        f'heart-rate,device-id=legacy-plain value=62 {stamp}',
        f'heart-rate,device-id-reference=Patient/participant-a,source-device-id=other-phone,source-key=source-b value=84 {stamp}',
    ]
    (tmp_path / "input.lp").write_text("\n".join(lines) + "\n")
    (tmp_path / "telegraf.conf").write_text('''[agent]
  omit_hostname = true
[[inputs.file]]
  files = ["/identity/input.lp"]
  data_format = "influx"
[[processors.starlark]]
  source = \x27\x27\x27
''' + processor + "\n'''\n")
    # Match the owner of pytest's private directory on Linux. No root access is needed.
    output = docker("run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}", "-v", f"{tmp_path}:/identity:ro", "telegraf:1.36",
                    "telegraf", "--config", "/identity/telegraf.conf", "--test")
    stored = [line.removeprefix("> ") for line in output.splitlines()
              if line.startswith(("heart-rate,", "> heart-rate,"))]
    assert len(stored) == 5, output
    assert any("source-device-id=shared-phone" in s and "device-id=participant-a" in s for s in stored)
    name = "wearables-grafana-identity-" + uuid4().hex[:12]
    token = "synthetic-grafana-identity-" + uuid4().hex
    started = False
    try:
        docker("run", "-d", "--name", name, "-p", "127.0.0.1::8086",
               "-e", "DOCKER_INFLUXDB_INIT_MODE=setup", "-e", "DOCKER_INFLUXDB_INIT_USERNAME=synthetic",
               "-e", "DOCKER_INFLUXDB_INIT_PASSWORD=synthetic-test-password", "-e", "DOCKER_INFLUXDB_INIT_ORG=identity_test",
               "-e", "DOCKER_INFLUXDB_INIT_BUCKET=identity_test", "-e", "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=" + token,
               "influxdb:2.7")
        started = True
        port = json.loads(docker("inspect", name))[0]["NetworkSettings"]["Ports"]["8086/tcp"][0]["HostPort"]
        with httpx.Client(base_url="http://127.0.0.1:" + port, headers={"Authorization": "Token " + token}) as client:
            deadline = time.monotonic() + 90
            while True:
                try:
                    orgs = client.get("/api/v2/orgs", params={"org": "identity_test"})
                    if orgs.status_code == 200 and orgs.json().get("orgs"):
                        break
                except httpx.HTTPError:
                    pass
                assert time.monotonic() < deadline, "Disposable InfluxDB did not start"
                time.sleep(0.5)
            org_id = orgs.json()["orgs"][0]["id"]
            bucket_id = client.get("/api/v2/buckets", params={"orgID": org_id, "name": "identity_test"}).json()["buckets"][0]["id"]
            response = client.post("/api/v2/dbrps", json={"orgID": org_id, "bucketID": bucket_id,
                "database": "identity_test", "retention_policy": "autogen", "default": True})
            assert response.status_code == 201, response.text
            response = client.post("/api/v2/write", params={"org": "identity_test", "bucket": "identity_test", "precision": "ns"},
                                   content="\n".join(stored))
            assert response.status_code == 204, response.text

            def query(q):
                response = client.get("/query", params={"db": "identity_test", "q": q})
                assert response.status_code == 200, response.text
                result = response.json()["results"][0]
                assert "error" not in result, result
                return result.get("series", [])

            for path in DASHBOARDS:
                dashboard = json.loads(path.read_text())
                panel = next(t for t in targets(dashboard) if 'FROM "heart-rate"' in t["query"] and 'mean(' in t["query"])
                for participant, value in [("participant-a", 72), ("participant-b", 99), ("legacy-participant", 61)]:
                    q = panel["query"].replace("$timeFilter", "time > now() - 1h").replace("$__interval", "1m")
                    q = q.replace("$deviceId", participant).replace("$sourceKey", "source-a")
                    series = query(q)
                    assert len(series) == 1
                    assert [row[1] for row in series[0]["values"] if row[1] is not None] == [value], (path.name, participant, series)
                legacy_query = panel["query"].replace("$timeFilter", "time > now() - 1h").replace("$__interval", "1m")
                legacy_query = legacy_query.replace("$deviceId", "legacy-plain").replace("$sourceKey", ".*")
                legacy_series = query(legacy_query)
                assert len(legacy_series) == 1
                assert [row[1] for row in legacy_series[0]["values"] if row[1] is not None] == [62]
                variables = {v["name"]: v for v in dashboard["templating"]["list"]}
                ids = {row[1] for s in query(variables["deviceId"]["query"]) for row in s["values"]}
                assert ids == {"participant-a", "participant-b", "legacy-participant", "legacy-plain"}
                sources = query(variables["sourceKey"]["query"].replace("$deviceId", "participant-a"))
                assert {row[1] for s in sources for row in s["values"]} == {"source-a", "source-b"}
            # Query individual sensor and sleep series with shared hardware across participants.
            dashboard = json.loads(DASHBOARDS[0].read_text())
            for title, measurement, target_index, value, expected in [
                ("Skin Temperature", "skin-temperature", 0, 32.5, 32.5),
                ("Pulse-to-Pulse Interval", "pulse-to-pulse-interval", 0, 800.0, 800.0),
                ("Sleep Stages (One Night)", "sleep-rem", 1, 20.0, 3),
                ("Sleep Stages (One Night)", "sleep-deep", 3, 10.0, 1),
            ]:
                values = [("participant-a", "source-a", value),
                          ("participant-b", "source-a", value + 2),
                          ("participant-a", "source-b", value + 4)]
                payload = "\n".join(f"{measurement},device-id={pid},source-key={source} value={value} {stamp}"
                                    for pid, source, value in values)
                write = client.post("/api/v2/write", params={"org": "identity_test", "bucket": "identity_test",
                                    "precision": "ns"}, content=payload)
                assert write.status_code == 204, write.text
                panel = next(p for p in dashboard["panels"] if p["title"] == title)
                q = panel["targets"][target_index]["query"].replace("$timeFilter", "time > now() - 1h")
                q = q.replace("$__interval", "1m").replace("$deviceId", "participant-a").replace("$sourceKey", "source-a")
                result = query(q)
                assert len(result) == 1
                assert [row[1] for row in result[0]["values"] if row[1] is not None] == [expected]
    finally:
        if started:
            docker("rm", "--force", "--volumes", name)
