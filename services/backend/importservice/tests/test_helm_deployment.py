"""Rendered deployment contracts across importer, mapper and Kafka charts."""

import base64
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from app.config import Settings

ROOT = Path(__file__).resolve().parents[4]
HELM = os.getenv("HELM_BINARY") or shutil.which("helm")
pytestmark = pytest.mark.skipif(not HELM, reason="Helm 3+ is required for deployment contract checks")


def render(chart, *arguments, image=True, success=True):
    command = [HELM, "template", "review", str(ROOT / "gitops/apps" / chart)]
    if image:
        command += ["--set", "image.tag=review-commit"]
    result = subprocess.run(command + list(arguments), capture_output=True, text=True, check=False)
    if not success:
        assert result.returncode != 0
        return result.stderr
    assert result.returncode == 0, result.stderr
    return [document for document in yaml.safe_load_all(result.stdout) if document]


def resource(documents, kind, name=None):
    return next(d for d in documents if d["kind"] == kind and (name is None or d["metadata"]["name"] == name))


def container(document):
    return document["spec"]["template"]["spec"]["containers"][0]


def test_importer_runtime_configuration_matches_application_and_exposes_no_secrets(monkeypatch):
    documents = render("services/importservice")
    config = resource(documents, "ConfigMap")["data"]
    for key, value in config.items():
        assert isinstance(value, str)
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("INGEST_DATABASE_URL", "postgresql://example/ingestion")
    monkeypatch.setenv("JWT_SECRET", "synthetic-test-" + "x" * 32)
    monkeypatch.setenv("INGEST_ARCHIVE_KEY", base64.b64encode(b"a" * 32).decode())
    monkeypatch.setenv("INGEST_SIGNING_KEY", base64.b64encode(b"s" * 32).decode())
    Settings().validate()
    deploy = resource(documents, "Deployment")
    runtime = container(deploy)
    assert runtime["readinessProbe"]["httpGet"]["path"] == "/ready"
    assert runtime["livenessProbe"]["httpGet"]["path"] == "/health"
    references = {entry["name"]: entry["valueFrom"]["secretKeyRef"] for entry in runtime["env"]}
    required = {"JWT_SECRET", "INGEST_DATABASE_URL", "INGEST_ARCHIVE_KEY", "INGEST_SIGNING_KEY", "INFLUXDB_TOKEN"}
    assert required <= references.keys()
    assert required.isdisjoint(config)
    assert not any(d["kind"] == "Secret" for d in documents)
    assert not deploy["spec"]["template"]["spec"]["automountServiceAccountToken"]


def test_migration_runs_before_install_upgrade_with_separate_database_authority():
    documents = render("services/importservice")
    runtime, job = resource(documents, "Deployment"), resource(documents, "Job")
    annotations = job["metadata"]["annotations"]
    assert annotations["helm.sh/hook"] == "pre-install,pre-upgrade"
    migration = container(job)
    assert migration["image"] == container(runtime)["image"]
    assert migration["command"] == ["python", "-m", "app.migrate"]
    assert {entry["name"] for entry in migration["env"]} == {"INGEST_DATABASE_URL", "INGEST_RUNTIME_ROLE"}
    runtime_ref = next(e for e in container(runtime)["env"] if e["name"] == "INGEST_DATABASE_URL")
    migration_ref = next(e for e in migration["env"] if e["name"] == "INGEST_DATABASE_URL")
    assert runtime_ref["valueFrom"]["secretKeyRef"]["name"] != migration_ref["valueFrom"]["secretKeyRef"]["name"]
    assert "must differ" in render(
        "services/importservice", "--set", "migration.secretName=importservice-ingestion", success=False
    )


def test_mapper_and_importer_share_signing_and_results_contract_without_archive_access():
    importer = render("services/importservice")
    mapper = render("services/mapper-validator")
    worker = container(resource(mapper, "Deployment"))
    env = resource(mapper, "ConfigMap", "mapper-app-env-config")["data"]
    signing = next(e for e in worker["env"] if e["name"] == "INGEST_SIGNING_KEY")
    sender_signing = next(
        e for e in container(resource(importer, "Deployment"))["env"] if e["name"] == "INGEST_SIGNING_KEY"
    )
    assert signing == sender_signing
    assert {e["name"] for e in worker["env"]} == {"INGEST_SIGNING_KEY"}
    topics = resource(importer, "ConfigMap")["data"]
    assert env["RESULTS_TOPIC"] == topics["KAFKA_RESULTS_TOPIC"]
    assert env["INPUT_TOPIC"] == topics["KAFKA_TOPIC"]
    assert env["OUTPUT_TOPIC"] == topics["KAFKA_OUTPUT_TOPIC"]
    kafka = render("platform/kafka", image=False)
    result_topic = resource(kafka, "KafkaTopic", env["RESULTS_TOPIC"])
    assert result_topic["spec"]["replicas"] == 3
    assert result_topic["spec"]["partitions"] == 30


def test_deployed_mapping_preserves_separate_participant_and_collector():
    docs = render("services/mapper-validator")
    mapping = yaml.safe_load(resource(docs, "ConfigMap", "mapping-config")["data"]["mapping.yaml"])
    bundled = yaml.safe_load(
        (ROOT / "services/backend/fhir-mapper-validator/config/mapping-2026-01-28.yaml").read_text()
    )
    assert mapping == bundled
    for name in [
        "services/backend/fhir-mapper-validator/src/main/resources/mapping-2026-01-28.yaml",
        "services/backend/extraction-service/src/app/default_fhir_mapping.yaml",
    ]:
        assert yaml.safe_load((ROOT / name).read_text()) == mapping
    fields = {f["target"]: f for f in mapping["metadata"]["fields"]}
    assert fields["subject.reference"]["rawSource"] == "participantId"
    assert fields["device.display"]["rawSource"] == "deviceInfo.deviceId"
    assert fields["device.display"]["lineProtocol"]["name"] == "source-device-id"


@pytest.mark.parametrize("chart", ["services/importservice", "services/mapper-validator"])
def test_default_images_preserve_argocd_latest_always_policy(chart):
    documents = render(chart, image=False)
    runtime = container(resource(documents, "Deployment"))
    assert runtime["image"].endswith(":latest")
    assert runtime["imagePullPolicy"] == "Always"
    if "importservice" in chart:
        assert container(resource(documents, "Job"))["image"] == runtime["image"]
        assert container(resource(documents, "Job"))["imagePullPolicy"] == "Always"


@pytest.mark.parametrize("chart", ["services/importservice", "services/mapper-validator"])
def test_images_still_support_pinned_tags_digests_and_reject_empty_selectors(chart):
    pinned = container(resource(render(chart), "Deployment"))
    assert pinned["image"].endswith(":review-commit")
    assert "Set image.tag" in render(chart, "--set", "image.tag=", image=False, success=False)
    digest = "sha256:" + "a" * 64
    documents = render(chart, "--set", "image.digest=" + digest, image=False)
    assert container(resource(documents, "Deployment"))["image"].endswith("@" + digest)


def test_bff_uses_existing_secret_without_embedded_credentials_and_keeps_browser_security():
    documents = render("services/wearables-bff", image=False)
    assert not any(d["kind"] == "Secret" for d in documents)
    runtime = container(resource(documents, "Deployment"))
    assert runtime["image"].endswith(":latest")
    assert runtime["imagePullPolicy"] == "Always"
    assert {"secretRef": {"name": "wearables-bff-secrets"}} in runtime["envFrom"]
    config = resource(documents, "ConfigMap")["data"]
    assert config["COOKIE_SECURE"] == "true"
    for key in ("BACKEND_URL", "FRONTEND_REDIRECT_URL", "FRONTEND_ORIGINS"):
        assert config[key].startswith("https://")
    for key in ("JWT_SECRET", "CONTROL_WRITE_TOKEN", "API_TOKEN_SERVICE_TOKEN", "DATABASE_OPERATOR_TOKEN", "BREVO_API_KEY"):
        assert key not in config


def test_operator_configured_bff_chart_starts_in_production_with_email_disabled():
    documents = render(
        "services/wearables-bff", "--set", "env.DATABASE_API_URL=https://authority.example.test", image=False
    )
    bff = ROOT / "services/backend/wearables-bff"
    environment = {
        **os.environ, **resource(documents, "ConfigMap")["data"],
        "BREVO_API_KEY": "disabled",
        "JWT_SECRET": "synthetic-rendered-production-jwt-at-least-32",
        "CONTROL_WRITE_TOKEN": "synthetic-rendered-control-writer",
        "API_TOKEN_SERVICE_TOKEN": "synthetic-rendered-api-token-service",
        "DATABASE_OPERATOR_TOKEN": "synthetic-rendered-database-operator-32",
        "ALLOW_DEV_AUTH_BYPASS": "false",
    }
    script = (
        "const {config}=await import('./src/config.ts');"
        "console.log(JSON.stringify({production:config.isProduction,"
        "email:config.emailDeliveryEnabled,secureCookie:config.cookieSecure,bypass:config.devAuthBypass}));"
    )
    result = subprocess.run(
        ["node", "--import", "tsx", "--input-type=module", "-e", script],
        cwd=bff, env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"production": True, "email": False, "secureCookie": True, "bypass": False}


def test_grafana_chart_can_wire_current_account_authority():
    documents = render(
        "monitoring/grafana-proxy", "--set", "session.authApiUrl=https://authority.example.test/api/me", image=False
    )
    assert resource(documents, "ConfigMap")["data"]["AUTH_API_URL"] == "https://authority.example.test/api/me"


@pytest.mark.parametrize("chart", ["services/importservice", "services/mapper-validator"])
def test_configuration_changes_trigger_rollout(chart):
    first = resource(render(chart), "Deployment")["spec"]["template"]["metadata"]["annotations"]
    option = "env.KAFKA_RESULTS_TOPIC=other-results" if "importservice" in chart else "envs.resultsTopic=other-results"
    second = resource(render(chart, "--set", option), "Deployment")["spec"]["template"]["metadata"]["annotations"]
    assert first["checksum/config"] != second["checksum/config"]


@pytest.mark.parametrize(
    "chart,key",
    [
        ("services/importservice", "KAFKA_SECURITY_JSON"),
        ("services/mapper-validator", "KAFKA_SECURITY_PROPERTIES_JSON"),
    ],
)
def test_kafka_transport_credentials_are_secret_references(chart, key):
    deploy = resource(render(chart, "--set", "kafkaSecuritySecret.name=kafka-transport"), "Deployment")
    entry = next(e for e in container(deploy)["env"] if e["name"] == key)
    assert entry["valueFrom"]["secretKeyRef"] == {"name": "kafka-transport", "key": key}
