"""PostgreSQL upload archive, immutable identities and leased delivery journal."""

import json
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .contracts import INPUT_KIND, Conflict
from .crypto import sign
from .projection import prepare_projection


class QuotaExceeded(Exception):
    pass


class Repository:
    def __init__(self, settings, cipher):
        self.settings, self.cipher = settings, cipher
        self.pool = AsyncConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=8,
            max_waiting=32,
            timeout=5,
            open=False,
            kwargs={"row_factory": dict_row, "options": "-c statement_timeout=5000 -c lock_timeout=3000"},
        )

    async def open(self):
        await self.pool.open(wait=True, timeout=10)
        async with self.pool.connection() as conn:
            await conn.execute("SELECT id FROM ingestion.uploads LIMIT 0")
            keys = await (
                await conn.execute(
                    "SELECT archive_key_id FROM ingestion.records UNION SELECT archive_key_id FROM ingestion.uploads"
                )
            ).fetchall()
            if any(row["archive_key_id"] not in self.cipher.keys for row in keys):
                raise ValueError("An archive decryption key is missing")

    async def close(self):
        await self.pool.close()

    async def event(self, conn, code, record_id=None, upload_id=None, generation=None, mapper_version=None):
        await conn.execute(
            "INSERT INTO ingestion.events (code,record_id,upload_id,generation,mapper_version) VALUES (%s,%s,%s,%s,%s)",
            (code, record_id, upload_id, generation, mapper_version),
        )

    async def accept(self, upload):
        async with self.pool.connection() as conn, conn.transaction():
            # Serialize admission within a participant/case, including rate budgets.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (upload["case_id"] + ":" + upload["participant_id"],),
            )
            existing = await (
                await conn.execute(
                    "SELECT id,raw_sha256 FROM ingestion.uploads WHERE case_id=%s AND participant_id=%s AND request_key=%s",
                    (upload["case_id"], upload["participant_id"], upload["request_key"]),
                )
            ).fetchone()
            if existing:
                if existing["raw_sha256"] != upload["raw_sha256"]:
                    raise Conflict("An idempotency key was reused with different bytes")
                return str(existing["id"]), True
            budget = await (
                await conn.execute(
                    "SELECT count(*) AS n,coalesce(sum(raw_size),0) AS bytes FROM ingestion.uploads "
                    "WHERE case_id=%s AND participant_id=%s AND created_at > clock_timestamp()-interval '1 hour'",
                    (upload["case_id"], upload["participant_id"]),
                )
            ).fetchone()
            if budget["n"] >= 1000 or budget["bytes"] + len(upload["raw"]) > 50_000_000:
                raise QuotaExceeded()
            key_id, ciphertext = self.cipher.seal(upload["raw"], "upload:" + upload["id"])
            await conn.execute(
                "INSERT INTO ingestion.uploads "
                "(id,case_id,participant_id,request_key,raw_sha256,raw_size,archive_key_id,raw_ciphertext,reading_count) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    upload["id"],
                    upload["case_id"],
                    upload["participant_id"],
                    upload["request_key"],
                    upload["raw_sha256"],
                    len(upload["raw"]),
                    key_id,
                    ciphertext,
                    upload["reading_count"],
                ),
            )
            for record in sorted(upload["records"], key=lambda r: r["record_key"]):
                key_id, ciphertext = self.cipher.seal(record["payload"], "record:" + record["id"])
                row = await (
                    await conn.execute(
                        "INSERT INTO ingestion.records (id,first_upload_id,record_key,input_sha256,source_key,"
                        "identity_mode,archive_key_id,payload_ciphertext) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                        "ON CONFLICT (record_key) DO NOTHING RETURNING id,input_sha256",
                        (
                            record["id"],
                            upload["id"],
                            record["record_key"],
                            record["input_sha256"],
                            record["source_key"],
                            record["identity_mode"],
                            key_id,
                            ciphertext,
                        ),
                    )
                ).fetchone()
                if row is None:
                    row = await (
                        await conn.execute(
                            "SELECT id,input_sha256 FROM ingestion.records WHERE record_key=%s", (record["record_key"],)
                        )
                    ).fetchone()
                    if row["input_sha256"] != record["input_sha256"]:
                        raise Conflict("An immutable source record changed")
                else:
                    await conn.execute(
                        "INSERT INTO ingestion.outbox (record_id,generation,stage) VALUES (%s,1,'raw')", (row["id"],)
                    )
                await conn.execute(
                    "INSERT INTO ingestion.upload_records VALUES (%s,%s) ON CONFLICT DO NOTHING",
                    (upload["id"], row["id"]),
                )
            await self.event(conn, "archived", upload_id=upload["id"])
        # No response is returned until the transaction has committed.
        return upload["id"], False

    async def receipt(self, upload_id, claims):
        async with self.pool.connection() as conn:
            upload = await (
                await conn.execute(
                    "SELECT id,raw_sha256,reading_count FROM ingestion.uploads WHERE id=%s AND case_id=%s AND participant_id=%s",
                    (upload_id, claims["caseId"], claims["patientId"]),
                )
            ).fetchone()
            if upload is None:
                return None
            counts = await (
                await conn.execute(
                    "SELECT count(*) AS records, count(*) FILTER (WHERE r.identity_mode='source-record') AS identified, "
                    "count(*) FILTER (WHERE r.outcome='normalized') AS normalized, "
                    "count(*) FILTER (WHERE r.outcome='rejected') AS rejected, "
                    "count(*) FILTER (WHERE r.confirmed_at IS NOT NULL) AS stored, "
                    "count(*) FILTER (WHERE r.result_conflict) AS conflicts, "
                    "count(*) FILTER (WHERE o.state='confirmed') AS broker, "
                    "count(*) FILTER (WHERE o.state='blocked' OR p.state='blocked') AS blocked "
                    "FROM ingestion.upload_records ur JOIN ingestion.records r ON r.id=ur.record_id "
                    "LEFT JOIN ingestion.outbox o ON o.record_id=r.id AND o.generation=r.generation AND o.stage='raw' "
                    "LEFT JOIN ingestion.outbox p ON p.record_id=r.id AND p.generation=r.generation AND p.stage='projection' "
                    "WHERE ur.upload_id=%s",
                    (upload_id,),
                )
            ).fetchone()
            if counts["conflicts"]:
                progress = "needs-review"
            elif counts["blocked"]:
                progress = "blocked"
            elif counts["stored"] == counts["records"]:
                progress = "storage-observed"
            elif counts["rejected"] + counts["stored"] == counts["records"]:
                progress = "partially-rejected" if counts["stored"] else "rejected"
            elif counts["normalized"]:
                progress = "awaiting-storage"
            else:
                progress = "awaiting-processing" if counts["broker"] else "awaiting-delivery"
            return {
                "processingState": progress,
                "acceptanceId": str(upload["id"]),
                "rawSha256": upload["raw_sha256"],
                "status": "archived",
                "readingCount": upload["reading_count"],
                "recordCount": counts["records"],
                "sourceIdentifiedCount": counts["identified"],
                "brokerConfirmedCount": counts["broker"],
                "normalizedCount": counts["normalized"],
                "rejectedCount": counts["rejected"],
                "storedConfirmedCount": counts["stored"],
                "blockedCount": counts["blocked"],
                "conflictCount": counts["conflicts"],
                "total_messages_produced": counts["broker"],
            }

    async def claim(self):
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "SELECT o.record_id,o.stage,o.generation,o.attempts FROM ingestion.outbox o "
                    "JOIN ingestion.records r ON r.id=o.record_id AND r.generation=o.generation "
                    "WHERE o.available_at<=clock_timestamp() AND (o.state='pending' OR "
                    "(o.state='leased' AND o.lease_until<clock_timestamp())) AND "
                    "((o.stage='raw' AND r.outcome='pending') OR "
                    "(o.stage='projection' AND r.outcome='normalized' AND r.confirmed_at IS NULL)) "
                    "ORDER BY o.available_at FOR UPDATE OF o SKIP LOCKED LIMIT 1"
                )
            ).fetchone()
            if row is None:
                return None
            lease = uuid4()
            await conn.execute(
                "UPDATE ingestion.outbox SET state='leased',lease_id=%s,lease_until=clock_timestamp()+%s*interval '1 second',"
                "attempts=attempts+1,updated_at=clock_timestamp() WHERE record_id=%s AND generation=%s AND stage=%s",
                (lease, self.settings.lease_seconds, row["record_id"], row["generation"], row["stage"]),
            )
            record = await (
                await conn.execute(
                    "SELECT r.*,u.raw_sha256 FROM ingestion.records r JOIN ingestion.uploads u ON u.id=r.first_upload_id "
                    "WHERE r.id=%s",
                    (row["record_id"],),
                )
            ).fetchone()
            if row["stage"] == "raw":
                data = json.loads(
                    self.cipher.open(
                        record["archive_key_id"], record["payload_ciphertext"], "record:" + str(record["id"])
                    )
                )
                body = {
                    "recordId": str(record["id"]),
                    "uploadId": str(record["first_upload_id"]),
                    "generation": row["generation"],
                    "inputSha256": record["input_sha256"],
                    "rawSha256": record["raw_sha256"],
                    "sourceKey": record["source_key"],
                    "identityMode": record["identity_mode"],
                    "data": data,
                }
                wire = sign(body, self.settings.decode_key(self.settings.signing_key_b64), INPUT_KIND)
                topic = self.settings.kafka_topic
            else:
                wire = self.cipher.open(
                    record["archive_key_id"], record["output_ciphertext"], "output:" + str(record["id"])
                )
                topic = self.settings.kafka_output_topic
            return {**row, "lease_id": lease, "wire": wire, "topic": topic}

    async def finish(self, job, broker=None):
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "UPDATE ingestion.outbox SET state=%s,broker_partition=%s,broker_offset=%s,error_code=%s,"
                    "lease_until=NULL,available_at=clock_timestamp()+%s*interval '1 second',updated_at=clock_timestamp() "
                    "WHERE record_id=%s AND generation=%s AND stage=%s AND state='leased' AND lease_id=%s "
                    "RETURNING record_id",
                    (
                        "confirmed"
                        if broker
                        else "blocked"
                        if job["attempts"] + 1 >= self.settings.max_attempts
                        else "pending",
                        broker[0] if broker else None,
                        broker[1] if broker else None,
                        None if broker else "broker_delivery_failed",
                        min(2 ** min(job["attempts"] + 1, 8), 300),
                        job["record_id"],
                        job["generation"],
                        job["stage"],
                        job["lease_id"],
                    ),
                )
            ).fetchone()
            if row:
                await self.event(
                    conn,
                    job["stage"] + ("_broker_confirmed" if broker else "_delivery_failed"),
                    record_id=job["record_id"],
                    generation=job["generation"],
                )

    async def apply_result(self, result):
        async with self.pool.connection() as conn, conn.transaction():
            row = await (
                await conn.execute(
                    "SELECT r.*,u.raw_sha256 FROM ingestion.records r JOIN ingestion.uploads u ON u.id=r.first_upload_id "
                    "WHERE r.id=%s FOR UPDATE OF r",
                    (result["recordId"],),
                )
            ).fetchone()
            if row is None or row["generation"] != result["generation"] or row["input_sha256"] != result["inputSha256"]:
                return "stale"
            if row["outcome"] != "pending":
                conflicting = row["outcome"] != result["status"] or row["mapper_version"] != result["mapperVersion"]
                if not conflicting and result["status"] == "normalized":
                    try:
                        _, candidate, _, _ = prepare_projection(result["lineProtocol"], row, result["mapperVersion"])
                        conflicting = candidate != row["output_sha256"]
                    except (ValueError, KeyError):
                        conflicting = True
                if conflicting and not row["result_conflict"]:
                    await conn.execute("UPDATE ingestion.records SET result_conflict=true WHERE id=%s", (row["id"],))
                    await self.event(
                        conn,
                        "processing_result_conflict",
                        record_id=row["id"],
                        generation=row["generation"],
                        mapper_version=result["mapperVersion"],
                    )
                return "conflict" if conflicting else "duplicate"
            error = result.get("errorCode")
            if result["status"] == "normalized":
                try:
                    point_key, output_hash, wire, timestamp = prepare_projection(
                        result["lineProtocol"], row, result["mapperVersion"]
                    )
                except (ValueError, KeyError):
                    error = "invalid_projection"
                else:
                    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,1))", (point_key,))
                    owner = await (
                        await conn.execute("SELECT id FROM ingestion.records WHERE projection_key=%s", (point_key,))
                    ).fetchone()
                    if owner and owner["id"] != row["id"]:
                        error = "projection_collision"
                    else:
                        _, ciphertext = self.cipher.seal(wire, "output:" + str(row["id"]), row["archive_key_id"])
                        await conn.execute(
                            "UPDATE ingestion.records SET outcome='normalized',mapper_version=%s,projection_key=%s,"
                            "output_sha256=%s,output_ciphertext=%s,timestamp_ns=%s,updated_at=clock_timestamp() WHERE id=%s",
                            (result["mapperVersion"], point_key, output_hash, ciphertext, timestamp, row["id"]),
                        )
                        await conn.execute(
                            "INSERT INTO ingestion.outbox (record_id,generation,stage) VALUES (%s,%s,'projection')",
                            (row["id"], row["generation"]),
                        )
            if error:
                await conn.execute(
                    "UPDATE ingestion.records SET outcome='rejected',error_code=%s,mapper_version=%s,"
                    "updated_at=clock_timestamp() WHERE id=%s",
                    (error, result["mapperVersion"], row["id"]),
                )
            await self.event(
                conn,
                "rejected_" + error if error else "normalized",
                record_id=row["id"],
                generation=row["generation"],
                mapper_version=result["mapperVersion"],
            )
            return "rejected" if error else "normalized"

    async def recover_stalled(self):
        async with self.pool.connection() as conn:
            # Replay original input when a processing result was lost; replay the exact
            # stored projection when the downstream point has not been observed.
            await conn.execute(
                "UPDATE ingestion.outbox o SET state=CASE WHEN attempts>=%s THEN 'blocked' ELSE 'pending' END,"
                "available_at=clock_timestamp(),updated_at=clock_timestamp() FROM ingestion.records r "
                "WHERE r.id=o.record_id AND r.generation=o.generation AND o.state='confirmed' "
                "AND o.updated_at<clock_timestamp()-%s*interval '1 second' AND "
                "((o.stage='raw' AND r.outcome='pending') OR "
                "(o.stage='projection' AND r.outcome='normalized' AND r.confirmed_at IS NULL))",
                (self.settings.max_attempts, self.settings.replay_seconds),
            )

    async def retry(self, upload_id, claims):
        async with self.pool.connection() as conn, conn.transaction():
            upload = await (
                await conn.execute(
                    "SELECT id FROM ingestion.uploads WHERE id=%s AND case_id=%s AND participant_id=%s FOR UPDATE",
                    (upload_id, claims["caseId"], claims["patientId"]),
                )
            ).fetchone()
            if upload is None:
                return None
            records = await (
                await conn.execute(
                    "SELECT r.id,r.generation,r.outcome FROM ingestion.upload_records ur JOIN ingestion.records r ON r.id=ur.record_id "
                    "WHERE ur.upload_id=%s ORDER BY r.id FOR UPDATE OF r",
                    (upload_id,),
                )
            ).fetchall()
            retried = 0
            for row in records:
                # The participant can retry failed work, not overwrite a successful result.
                if row["outcome"] == "rejected":
                    generation = row["generation"] + 1
                    if generation > 5:
                        continue
                    await conn.execute(
                        "UPDATE ingestion.records SET generation=%s,outcome='pending',error_code=NULL,"
                        "updated_at=clock_timestamp() WHERE id=%s",
                        (generation, row["id"]),
                    )
                    await conn.execute(
                        "INSERT INTO ingestion.outbox (record_id,generation,stage) VALUES (%s,%s,'raw')",
                        (row["id"], generation),
                    )
                    await self.event(conn, "owner_retry", row["id"], upload_id, generation)
                    retried += 1
                else:
                    changed = await conn.execute(
                        "UPDATE ingestion.outbox SET state='pending',attempts=0,available_at=clock_timestamp() "
                        "WHERE record_id=%s AND generation=%s AND state='blocked'",
                        (row["id"], row["generation"]),
                    )
                    retried += changed.rowcount
            return retried

    async def unconfirmed(self):
        async with self.pool.connection() as conn:
            return await (
                await conn.execute(
                    "WITH candidates AS (SELECT r.id FROM ingestion.records r JOIN ingestion.outbox o "
                    "ON o.record_id=r.id AND o.generation=r.generation AND o.stage='projection' "
                    "WHERE r.outcome='normalized' AND r.confirmed_at IS NULL AND o.state='confirmed' "
                    "AND r.next_observation_at<=clock_timestamp() ORDER BY r.next_observation_at "
                    "FOR UPDATE OF r SKIP LOCKED LIMIT 16) "
                    "UPDATE ingestion.records r SET next_observation_at=clock_timestamp()+interval '10 seconds' "
                    "FROM candidates c WHERE r.id=c.id RETURNING r.id,r.generation,r.output_sha256,r.timestamp_ns"
                )
            ).fetchall()

    async def confirm_storage(self, row):
        async with self.pool.connection() as conn, conn.transaction():
            cursor = await conn.execute(
                "UPDATE ingestion.records SET confirmed_at=clock_timestamp() "
                "WHERE id=%s AND generation=%s AND output_sha256=%s AND confirmed_at IS NULL",
                (row["id"], row["generation"], row["output_sha256"]),
            )
            if cursor.rowcount:
                await self.event(conn, "storage_observed", record_id=row["id"], generation=row["generation"])
