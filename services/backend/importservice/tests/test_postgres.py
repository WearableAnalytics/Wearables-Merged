import asyncio
import copy
import json
from uuid import uuid4

import pytest

from app.contracts import INPUT_KIND, Conflict, parse_upload
from app.crypto import verify
from app.repository import Repository

pytestmark = pytest.mark.integration


async def accept(repo, batch, claims, key=None):
    return await repo.accept(parse_upload(json.dumps(batch).encode(), claims, key, repo.settings))


async def result_for(repo, record_id, line=None, error=None):
    async with repo.pool.connection() as conn:
        row = await (await conn.execute("SELECT * FROM ingestion.records WHERE id=%s", (record_id,))).fetchone()
    body = {
        "recordId": str(record_id),
        "generation": row["generation"],
        "inputSha256": row["input_sha256"],
        "mapperVersion": "a" * 64,
        "status": "rejected" if error else "normalized",
    }
    if error:
        body["errorCode"] = error
    else:
        body["lineProtocol"] = (
            line or "heart-rate,device-id-reference=Patient/test value=72.12345678901234 1793355300000000000"
        )
    return body


async def test_committed_archive_survives_repository_reopen(repository, batch, claims):
    raw = json.dumps(batch, indent=2).encode()
    upload_id, _ = await repository.accept(parse_upload(raw, claims, None, repository.settings))
    async with repository.pool.connection() as conn:
        row = await (await conn.execute("SELECT * FROM ingestion.uploads WHERE id=%s", (upload_id,))).fetchone()
        assert bytes(row["raw_ciphertext"]) != raw
        assert repository.cipher.open(row["archive_key_id"], row["raw_ciphertext"], "upload:" + upload_id) == raw
    await repository.close()
    reopened = Repository(repository.settings, repository.cipher)
    await reopened.open()
    try:
        receipt = await reopened.receipt(upload_id, claims)
        assert receipt["status"] == "archived" and receipt["brokerConfirmedCount"] == 0
        assert await reopened.claim() is not None
    finally:
        await reopened.close()


async def test_concurrent_same_key_produces_one_archive_and_one_job(repository, batch, claims):
    results = await asyncio.gather(*(accept(repository, batch, claims, "retry-42") for _ in range(6)))
    assert len({r[0] for r in results}) == 1
    assert sum(not r[1] for r in results) == 1
    assert await repository.claim() is not None
    assert await repository.claim() is None


async def test_changed_bytes_with_same_key_are_rejected(repository, batch, claims):
    upload_id, _ = await accept(repository, batch, claims, "retry-42")
    batch["timestamp"] = "2026-10-30T12:00:00Z"
    with pytest.raises(Conflict):
        await accept(repository, batch, claims, "retry-42")
    assert (await repository.receipt(upload_id, claims))["recordCount"] == 1


async def test_new_upload_reuses_source_record_but_keeps_both_archives(repository, batch, claims):
    first, _ = await accept(repository, batch, claims)
    batch["timestamp"] = "2026-10-30T12:00:00Z"
    second, _ = await accept(repository, batch, claims)
    assert first != second
    async with repository.pool.connection() as conn:
        assert (await (await conn.execute("SELECT count(*) AS n FROM ingestion.records")).fetchone())["n"] == 1
        assert (await (await conn.execute("SELECT count(*) AS n FROM ingestion.uploads")).fetchone())["n"] == 2


async def test_source_conflict_rolls_back_the_whole_batch(repository, batch, claims):
    await accept(repository, batch, claims)
    batch["measurements"]["instantaneous"][0]["value"] = 75
    other = copy.deepcopy(batch["measurements"]["instantaneous"][0])
    other["sourceRecordId"] = "new-reading"
    batch["measurements"]["instantaneous"].insert(0, other)
    with pytest.raises(Conflict):
        await accept(repository, batch, claims)
    async with repository.pool.connection() as conn:
        assert (await (await conn.execute("SELECT count(*) AS n FROM ingestion.records")).fetchone())["n"] == 1
        assert (await (await conn.execute("SELECT count(*) AS n FROM ingestion.uploads")).fetchone())["n"] == 1


async def test_case_and_participant_scope_cannot_read_or_retry_another_upload(repository, batch, claims):
    upload_id, _ = await accept(repository, batch, claims)
    for field in ("caseId", "patientId"):
        other = {**claims, field: str(uuid4())}
        assert await repository.receipt(upload_id, other) is None
        assert await repository.retry(upload_id, other) is None


async def test_worker_keeps_sender_and_attested_participant_separate(repository, batch, claims):
    await accept(repository, batch, claims)
    job = await repository.claim()
    body = verify(job["wire"], repository.settings.decode_key(repository.settings.signing_key_b64), INPUT_KIND)
    assert body["data"]["deviceInfo"]["deviceId"] == "phone-installation-9"
    assert body["data"]["participantId"] == claims["patientId"]
    assert body["identityMode"] == "source-record"


async def test_expired_lease_is_reclaimed_and_old_worker_cannot_confirm_it(repository, batch, claims):
    await accept(repository, batch, claims)
    first = await repository.claim()
    async with repository.pool.connection() as conn:
        await conn.execute("UPDATE ingestion.outbox SET lease_until=clock_timestamp()-interval '1 second'")
    second = await repository.claim()
    assert first["lease_id"] != second["lease_id"]
    await repository.finish(first, (0, 12))
    async with repository.pool.connection() as conn:
        row = await (await conn.execute("SELECT state,lease_id FROM ingestion.outbox")).fetchone()
        assert row["state"] == "leased" and row["lease_id"] == second["lease_id"]
    await repository.finish(second, (0, 13))


async def test_results_are_idempotent_and_publication_is_not_storage_proof(repository, batch, claims):
    upload_id, _ = await accept(repository, batch, claims)
    job = await repository.claim()
    await repository.finish(job, (0, 1))
    result = await result_for(repository, job["record_id"])
    assert await repository.apply_result(result) == "normalized"
    assert await repository.apply_result(result) == "duplicate"
    projection = await repository.claim()
    assert projection["stage"] == "projection"
    wire = projection["wire"].decode()
    prefix, rest = wire.split(" ", 1)
    assert "ingestion-source=" in prefix and "ingestion_record_id=" not in prefix
    assert 'ingestion_record_id="' in rest and 'ingestion_raw_sha256="' in rest
    await repository.finish(projection, (1, 2))
    receipt = await repository.receipt(upload_id, claims)
    assert receipt["normalizedCount"] == 1 and receipt["storedConfirmedCount"] == 0
    row = (await repository.unconfirmed())[0]
    await repository.confirm_storage(row)
    assert (await repository.receipt(upload_id, claims))["storedConfirmedCount"] == 1


async def test_distinct_source_records_cannot_overwrite_the_same_database_point(repository, batch, claims):
    upload_id, _ = await accept(repository, batch, claims)
    batch["measurements"]["instantaneous"][0]["sourceRecordId"] = "different-record-same-instant"
    await accept(repository, batch, claims)
    first, second = await repository.claim(), await repository.claim()
    assert await repository.apply_result(await result_for(repository, first["record_id"])) == "normalized"
    assert await repository.apply_result(await result_for(repository, second["record_id"])) == "rejected"
    async with repository.pool.connection() as conn:
        row = await (
            await conn.execute("SELECT error_code FROM ingestion.records WHERE id=%s", (second["record_id"],))
        ).fetchone()
        assert row["error_code"] == "projection_collision"


async def test_two_sources_can_report_the_same_time_without_overwriting(repository, batch, claims):
    await accept(repository, batch, claims)
    batch["sourceId"] = "provider-account-other"
    await accept(repository, batch, claims)
    first, second = await repository.claim(), await repository.claim()
    assert await repository.apply_result(await result_for(repository, first["record_id"])) == "normalized"
    assert await repository.apply_result(await result_for(repository, second["record_id"])) == "normalized"


async def test_retry_fences_old_processing_generation(repository, batch, claims):
    upload_id, _ = await accept(repository, batch, claims)
    job = await repository.claim()
    old = await result_for(repository, job["record_id"])
    await repository.apply_result(await result_for(repository, job["record_id"], error="mapping_failed"))
    assert await repository.retry(upload_id, claims) == 1
    assert await repository.apply_result(old) == "stale"
    new = await repository.claim()
    assert new["generation"] == 2
    assert await repository.apply_result(await result_for(repository, new["record_id"])) == "normalized"
    assert await repository.retry(upload_id, claims) == 0


async def test_lost_processing_result_is_replayed_from_the_archive(repository, batch, claims):
    await accept(repository, batch, claims)
    job = await repository.claim()
    await repository.finish(job, (0, 10))
    async with repository.pool.connection() as conn:
        await conn.execute("UPDATE ingestion.outbox SET updated_at=clock_timestamp()-interval '1 hour'")
    await repository.recover_stalled()
    replay = await repository.claim()
    assert replay["wire"] == job["wire"]
    assert replay["record_id"] == job["record_id"] and replay["generation"] == job["generation"]


async def test_conflicting_processor_version_is_visible_without_overwriting_a_result(repository, batch, claims):
    upload_id, _ = await accept(repository, batch, claims)
    job = await repository.claim()
    first = await result_for(repository, job["record_id"])
    await repository.apply_result(first)
    assert await repository.apply_result({**first, "mapperVersion": "b" * 64}) == "conflict"
    assert (await repository.receipt(upload_id, claims))["conflictCount"] == 1
    async with repository.pool.connection() as conn:
        row = await (await conn.execute("SELECT mapper_version FROM ingestion.records")).fetchone()
        assert row["mapper_version"] == "a" * 64


async def test_missing_old_points_do_not_starve_new_storage_observations(repository, batch, claims):
    point = batch["measurements"]["instantaneous"][0]
    batch["measurements"]["instantaneous"] = [{**point, "sourceRecordId": f"reading-{i}"} for i in range(17)]
    await accept(repository, batch, claims)
    jobs = [await repository.claim() for _ in range(17)]
    for index, job in enumerate(jobs):
        await repository.apply_result(
            await result_for(repository, job["record_id"], line=f"heart-rate value=72 {1793355300000000000 + index}")
        )
    for _ in range(17):
        await repository.finish(await repository.claim(), (0, 42))
    first = await repository.unconfirmed()
    second = await repository.unconfirmed()
    assert len(first) == 16 and len(second) == 1
    assert {r["id"] for r in first}.isdisjoint({r["id"] for r in second})
