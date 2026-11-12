# Numeric source contract compatibility (#115, #118)

This small branch targets `reliable-ingestion`. It forwards the writer's
`sourceId` in each signed mapper input and bounds the optional native
`sourceDeviceId`. It accepts fractional interval/duration fields, including
the precise durations emitted by `measurement-mapping`.

The identity namespace and receipt protocol remain `wearables-numeric/1`.
The separate `wearables-numeric/2` setting belongs to the mapper configuration
and describes its numeric/units rules, not a replacement receipt protocol.
Existing integer duration inputs remain valid. Source-record fingerprints
normalize the advisory duration field before hashing, preserving the existing
fingerprint of historical whole-number inputs.

Apply this compatibility change when integrating the `measurement-mapping`
and `source-reconciliation` application branches with reliable ingestion.
The latter phone uploader opts into stable source-record identity only when
the native writer and record IDs are both available. Missing IDs retain the
legacy upload identity. Native device metadata is not an authentication claim.
