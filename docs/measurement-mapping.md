# Numeric measurement semantics (#115)

The `measurement-mapping` branch starts from main `1ab94f29`. It keeps the existing
numeric upload shapes and service entry points. Mapping version `2.0.0` opts into
`wearables-numeric/2` validation in the Java mapper.

## Changes

- Android's `BASAL_ENERGY_BURNED` adapter reads Health Connect basal metabolic
  rate in kcal/day. New phone uploads use instantaneous `BASAL_METABOLIC_RATE`
  and `KILOCALORIE_PER_DAY`. The mapper also recognizes the old Android batch
  representation. Apple resting energy remains cumulative energy in kcal.
- `SLEEP_LIGHT` and Apple's old core alias map to LOINC 93830-8. Deep and REM
  retain their own codes. RMSSD and SDNN remain distinct. RMSSD and basal rate
  use explicit local codes until the team approves an external terminology.
- Units of every mapped numeric type are checked before conversion. Supported
  conversions include km to m, seconds to milliseconds/minutes, and joules to
  kcal. Incompatible units, unknown metric mappings, negative values and
  non-finite values become rejected mapper outcomes rather than mislabeled data.
- The stored point retains the submitted value/unit, converted value/unit,
  coding, mapping version and timestamp interpretation. New cumulative and
  duration records preserve both interval endpoints through line protocol and
  FHIR export. Phone and Garmin duration values retain fractional minutes.
- Activity intervals use the base FHIR Observation profile and activity category.
  They no longer claim the Vital Signs profile, whose effective-time constraint
  rejects these interval resources. Every declared metric is checked with the
  HAPI validator, including the new period representation.
- Phone workout elapsed duration is explicit. A supplied active duration has a
  separate code and is not replaced with elapsed duration. Obtaining native pause
  events and session relationships remains Oskar's work in #117.
- The cloud publisher preserves RMSSD identity and UTC offsets. Offset-free
  legacy timestamps retain the existing UTC interpretation and receive the
  `legacy-assumed-utc` marker. This cannot recover a lost original timezone.
- Export uses a record's saved mapping when its ID is present. A lookup or
  validation failure propagates instead of substituting another mapping.
  Historical unversioned/1.x data uses the retained `legacy_fhir_mapping.yaml`.
  Stored coding, units and interval endpoints take precedence when available.
  Existing historical values are not rewritten. A later streaming export
  failure aborts that stream, so clients must check successful completion.

The canonical mapping is `fhir-mapper-validator/config/mapping-2026-01-28.yaml`.
Run `python3 scripts/sync-measurement-mapping.py` after editing it, and use
`--check` in verification. This copies the exact data to the bundled mapper,
export default and the mapping ConfigMap. No deployment parameters change.
New mappings need the matching Java and export code from this branch.

## Checks completed on 12 November 2026

- 36 Flutter tests passed, including Android/Apple basal semantics and duration
  precision. Tests used the local Flutter SDK's compatible test dependencies;
  the tracked lockfile stays at main's versions.
- 12 Java tests passed and the mapper JAR packaged. JUnit versions/discovery are
  pinned so both existing JUnit 4 and new JUnit 5 tests execute. The old graph
  test referenced an absent file and now checks the real mapping.
- 49 export tests and four cloud application tests passed.
- A Java-generated light-sleep line was decoded and exported by Python. The
  output retained the value, light-sleep code and microsecond interval endpoint.
- FHIR validator failures now propagate to the existing error path. The prior
  implementation caught its own failure. These are structural checks and do
  not establish clinical sensor accuracy.

The inventory of supported metrics is still the explicit mapping, extended by
light sleep, RMSSD and basal rate here. Other input types require their own
codes and unit policy. No clinical release approval or physical Android test
is claimed. Before combining with `reliable-ingestion`, its strict wire model
must also accept fractional duration fields. That compatibility change is
tracked with this issue's implementation.

References:
- https://developer.android.com/reference/kotlin/androidx/health/connect/client/records/BasalMetabolicRateRecord
- https://developer.apple.com/documentation/healthkit/hkquantitytypeidentifier/basalenergyburned
- https://loinc.org/93830-8/
- https://hl7.org/fhir/R4/observation-vitalsigns.html
- https://hl7.org/fhir/R4/observation.html
