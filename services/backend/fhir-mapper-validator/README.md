# FHIR Mapper + Validator (Kafka Streams)

Java/Kafka Streams application that ingests raw JSON from wearables, maps it to FHIR Observations using a YAML template, validates the result, converts valid resources to InfluxDB Line Protocol (LP), and routes problems to a DLQ.

## What runs where
- **Input topic** (`INPUT_TOPIC`, default `wearables-raw`): raw JSON payloads.
- **Output topic** (`OUTPUT_TOPIC`, default `wearables-lp`): LP lines ready for Influx.
- **DLQ topic** (`DLQ_TOPIC`, default `dlq`): wrapped JSON errors.
- **Config**: mapping YAML at `MAPPING_YAML_PATH` (default `config/json-to-fhir-new.yaml`).

Run via Kafka Streams; defaults are driven by env vars (see `org.example.config.Environment`).

## YAML template (deep dive)
Top-level keys: `version`, `metadata`, `measurement`.

### metadata
Static fields copied into every output document.
```yaml
metadata:
  fields:
    - name: device
      source: deviceInfo.deviceId   # JSON path in input
      target: device.display        # JSON path in FHIR output
      optional: false               # required if false
      type: string                  # hint for transforms/validation
      lineProtocol:                 # how this field participates in LP (optional)
        name: device-id
        type: tag                   # one of measurement|timestamp|tag|field
```

### measurement.paths
Each entry describes one measurement category (e.g., `instantaneous`, `duration`, `cumulative`). The `path` must point to an array in the incoming JSON. All array elements are mapped when `arrayMapAll: true` (the only supported mode).
```yaml
measurement:
  paths:
    - path: measurements.instantaneous
      arrayMapAll: true
      fields: [...]       # per-measurement fields (see below)
      mappings: [...]     # optional mapping tables used by transforms
```

### Fields
Each field describes how to populate a single FHIR element and optionally how it contributes to Line Protocol.
Key attributes:
- `name`: internal identifier.
- Exactly one of `source` (JSON path), `value` (literal), or `fhirSource` (pull from already-set FHIR path).
- `target`: JSON path in the output FHIR structure.
- `optional`: if false, missing/empty values make the measurement invalid.
- `type`: semantic hint (string/real/etc.).
- `transform`: ordered list of value transforms (see below).
- `lineProtocol`: how the field is used when rendering LP.

`lineProtocol.type` must follow Influx LP conventions:
- `measurement`: exactly one per category; becomes the LP measurement name.
- `timestamp`: exactly one per category; must resolve to an ISO-8601 string; converted to nanoseconds.
- `tag`: zero or more string tags.
- `field`: one or more fields; numeric values stay unquoted, strings get quoted.

Example field:
```yaml
- name: start
  source: measurements.instantaneous.timestamp
  target: effectiveDateTime
  transform:
    - type: append
      params: ["Z"]
  optional: false
  type: string
  lineProtocol:
    type: timestamp
```

### mappings (lookup tables)
Used by the `map` transform to convert one value to another (e.g., unit -> LOINC code/system).
```yaml
mappings:
  - fieldName: codingCode          # references a field's `name`
    valueType: string
    basedOnFhir: measurements.instantaneous.unit  # resolved value used as key
    map:
      - key: "BEATS_PER_MINUTE"
        value: "8867-4"
```

### Transforms (implemented)
Transforms are processed in order. Supported types (see `RawTransformer` / `FhirTransformer`):
- `toLowerCase`: lowercase string.
- `replace`: `params: ["from", "to"]` replace all.
- `append`: `params: ["suffix"]` append text.
- `substring`: `params: [start, end]` (0-based, end-exclusive).
- `map`: lookup via `mappings` table for the field.
- Partially implemented / logged as warnings: `prepend`, `flatMap`.
- Not yet supported: `combine` (throws).

### Dependency graph (LP minimization)
- Purpose: find the smallest set of fields that a FHIR can be minimized to without losing information (This set still needs to be valid Line Protocol)
- Base construction: groups fields that share the same raw `source` and prefer a base whose transforms are injective (append/replace/prepend assumed injective; toLowerCase/substring treated non-injective; map is injective only when the mapping table is bijective). Non-injective cases disable compression for that source.
- Enrichment: once base nodes exist, successors are added when a field’s `fhirSource` equals another field’s `target`, creating a dependency tree across derived FHIR fields.
- Mandatory LP coverage: `build()` ensures each category’s graph still contains exactly one `measurement`, one `timestamp`, and at least one `field` (per `lineProtocol.type`). Missing pieces raise configuration errors.
- Runtime use: the minimal node set is passed into `LineProtocolParser` so only required fields are read for LP rendering; this prevents mixing categories/configs.
- WIP: the dependency tree will continue to shrink LP output as injective detection improves and an upcoming `combine` transform can merge multiple FHIR fields into one LP element, further reducing mapped data.

## Runtime flow

### Startup (once per JVM)
1. Read env vars and set defaults (`INPUT_TOPIC`, `OUTPUT_TOPIC`, `DLQ_TOPIC`, `MAPPING_YAML_PATH`, `APP_ID`, `PARTITION_THREADS`, `KAFKA_BROKER_ENV_VAR`).
2. Load mapping YAML (`ConfigLoader` -> `MappingYaml`).
3. Validate YAML (`MappingYaml.validate`) to ensure version is set and field names are unique per category.
4. Initialize FHIR validator (`Validator.initializeFhirValidator`).
5. Build mapper instance with the YAML (`Mapper`).
6. Build dependency graph from YAML (`DependencyGraph`) and enrich with FHIR paths to derive the minimal node set required for LP per category (ensures measurement/timestamp/field/tag are present).
7. Build Kafka Streams topology: consume raw topic, map/validate, branch DLQ vs LP, produce to configured topics.
8. Start Kafka Streams and register shutdown hook.

### Per message (per Kafka record)
1. **Input**: Read raw JSON string from input topic. Empty/null payloads go straight to DLQ.
2. **Map to FHIR** (`Mapper.mapFhir`):
   - Parse JSON.
   - Build metadata block once.
   - For each measurement category (`measurement.paths`):
     - Iterate every element in the incoming array at `path` (requires `arrayMapAll: true`).
     - Apply metadata fields and per-category fields:
       - Resolve value from `source` / `value` / `fhirSource`.
       - Apply configured transforms.
       - Write to `target`; track required/optional status.
     - Collect per-category results into `valid` and `invalid` lists.
3. **Validate FHIR** (`Validator.validateFhir`): for each `valid` candidate in the category, run FHIR R5 validation. Failures are wrapped as DLQ entries; successes accumulate for LP conversion.
4. **Line Protocol conversion** (`LineProtocolParser.parse`): for each category with valid FHIR objects:
   - Use the minimal dependency set to locate required LP fields (measurement, timestamp, tags, fields).
   - Normalize ISO timestamps to nanoseconds; render LP string `measurement,tag-set field-set timestamp`.
   - Errors here are wrapped as DLQ entries with the offending FHIR payload.
5. **Branch and emit**:
   - DLQ-formatted JSON strings -> `DLQ_TOPIC`.
   - LP strings -> `OUTPUT_TOPIC`.

### DLQ payload shape
```json
{
  "valid": false,
  "error": "description of the failure",
  "payload": "original or intermediate payload"
}
```

## Files of interest
- `src/main/java/org/example/Main.java`: Kafka Streams topology and orchestration.
- `src/main/java/org/example/fhir/Mapper.java`: JSON -> FHIR mapping using YAML.
- `src/main/java/org/example/fhir/RawTransformer.java` and `FhirTransformer.java`: transform implementations.
- `src/main/java/org/example/lineprotocol/LineProtocolParser.java`: FHIR -> Influx LP rendering.
- `config/` and `src/main/resources/json-to-fhir-new.yaml`: example mapping templates.
- `outputs/`: sample valid/invalid outputs for reference.

# Further documentation

All documentation concerning deployment considerations can be found in `gitops/README.md`.

This file was compiled with the help of AI (ChatGPT 5.1. Codex Max)