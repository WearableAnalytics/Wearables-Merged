# Source-aware observations and views (#118)

Branch `source-reconciliation` builds on `measurement-mapping` (#115). Numeric
mapping version `2.1.0` adds source provenance without changing the receipt API.

## Identity through the application

- The phone sends the native writing application ID as `sourceId`, its platform
  as `sourcePlatform`, and each native sample UUID as `sourceRecordId`. A native
  measuring-device ID is included when supplied by the health API. The collector
  installation remains `deviceInfo.deviceId` and authentication remains separate.
- A phone batch opts into `wearables-numeric/1` when writer and record IDs exist.
  Missing IDs use legacy upload identity. They are never replaced with an
  invented sample ID. Identified and legacy readings do not share one batch.
- The importer binds participant/case identity from the verified token and
  preserves the submitted collector. The Garmin adapter sends an explicit
  participant and known Garmin writer namespace. It does not invent a physical
  Garmin device ID or a native sample ID when the provider response lacks them.
- The Java mapper retains writer, platform, sample and measuring-device metadata
  in fields. A SHA-256 source key over platform/writer/device is a series tag.
  Per-record UUIDs remain fields, avoiding a series per sample. String IDs such
  as `00123` remain strings. Unknown source identity receives the `legacy` key.
- Read/export deduplication includes native source identity. Equal values from
  two sources survive. Copies of the same identified reading forwarded by
  another collector collapse. Changed content under the same source record ID
  remains visible and prevents a reconciled total. FHIR observations have stable
  distinct identifiers and Bundle IDs across sources.
- Reads accept the existing `device-id`/FHIR reference tags and the explicit
  `patient-id`/`patient_id` tags used by Domingo's analytics work. An explicit
  patient identity takes precedence over a legacy tag when filtering results.

## Per-metric policies

`GET /v1/measurements/reconciled` is served through the existing authenticated
extraction proxy. Require one `patient_id`, one `measurement`, and offset-bearing
`start`/`end` values. A request spans at most 31 days and 10,000 unique readings.
This endpoint is read-only and does not modify raw observations.

The versioned policy is `source-selection/1`:

| Numeric category | Policy |
| --- | --- |
| Instantaneous, including heart rate, HRV and basal metabolic rate | Separate source samples. No cross-source average or energy total is inferred. |
| Cumulative, including steps, distance and energy amounts | Sum nonoverlapping complete intervals within one explicitly selected source. |
| Duration, one sleep stage or one workout-duration metric at a time | Sum nonoverlapping complete intervals within one explicitly selected source. Parent/session reconciliation is #117. |
| Unknown or legacy source | Show available observations and identity status. Do not infer a combined total. |

Modes:

- `mode=separate` is the default. It reports every source separately and has no
  combined selection. The response includes names, writer/device IDs, counts,
  unit, status and reported interval coverage.
- `mode=select&source_key=...` uses exactly the named source for that metric.
- `mode=priority&source_priority=...&source_priority=...` uses the first available
  source in the requested order for the whole window. This order is an explicit
  caller choice, not a sensor-accuracy claim. It does not fill source gaps from
  lower-ranked observations or distribute step counts proportionally in time.

Overlapping intervals within a source, conflicting native records, mixed units,
missing interval metadata and records crossing the requested boundary return an
explicit status with no numeric total. Coverage describes the reported records,
not a guarantee that the source captured all activity. The input window does
not recover records whose start precedes the queried storage window.

HealthKit statistics and Health Connect Activity/Sleep priority aggregation are
different native strategies. This implementation selects the explicit raw-source
policy above. The app's separate `totalStepsToday` metadata is not mixed into
raw measurement totals. Direct Garmin and phone records retain separate writer
namespaces, even when they describe the same activity.

All existing measurement/CSV/FHIR routes accept an optional `source_key` filter.
The standard and six-minute dashboards group by source and include a Source
selector. Selecting All compares distinct source series. Dashboard sums are
views of stored records; use the policy endpoint for overlap/conflict checks.
Sleep hour displays use the stored minute unit and include canonical light sleep.

## Verification and integration

Completed locally on 12 November 2026:

- 37 Flutter tests, 13 Java tests, 70 extraction/source-policy tests, four Garmin
  application tests, and an importer identity-boundary test passed.
- Cases include equal-valued distinct sources, native numeric-looking IDs,
  collector replacement, duplicate/conflicting IDs, overlapping intervals,
  legacy data, per-patient filtering, priority selection, size/time limits,
  interval boundaries, distinct FHIR Bundle IDs and dashboard source grouping.
- Follow-up checks cover finite-sum overflow, malformed legacy intervals,
  conflicting instantaneous IDs and scan limits even for mismatched patient
  results. The importer boundary test uses HTTP and works with both importer APIs.
  Mapper artifact tests create their own directories and do not depend on order.
- The original mapping checks and all declared numeric metrics also pass.
- A temporary local InfluxDB run verified source grouping including historical
  points without a source tag, and preserved native ID `00123` as a string.
  Its container and data were removed after the check.
- Tests use synthetic records. Physical provider synchronization and validation
  of platform-specific aggregation preferences require device testing.

When combining this branch with `reliable-ingestion`, apply the small
`ingestion-source-contract` follow-up too. It retains writer/device metadata in
the signed mapper input and accepts fractional duration fields. The reliable
journal supplies immutable-record admission and projection collision protection.
Plain main's older importer retains its earlier asynchronous delivery behavior.

Review this branch with Oskar's #116/#117 model changes, Domingo's patient tag,
and Philip/Arian's export work before integration. No schema or export policy
is silently changed on those other branches. Cloud/Kubernetes deployment
automation, credentials and release orchestration are outside this change.

References:
- https://developer.android.com/health-and-fitness/health-connect/aggregate-data
- https://developer.apple.com/documentation/healthkit/hkstatistics
