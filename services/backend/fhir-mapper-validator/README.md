# Protoype for Mapping and Validation

- This is the proof-of-concept implementation I did of the mapping and validation logic running inside Kafka Streams
- It's written in Java for the provided libraries but most importantly because Kafka Streams only support Java

# What does it do?

- Kafka Streams instance reads from the "raw" topic
- Takes the input and uses the yaml file to create a FHIR json (validity is the responsibility of the developer)
- When all fields are inserted into the json, it is validated using the FHIR library
- If validation is successful, it is parsed to LineProtocol and written to influx
- If validation is not successful, or an error occurs either in mapping to FHIR or LineProtocol the message is pushed to a DLQ

# Configure via YAML (state: 20.12.2025)

## Metadata and Measurements
- metadata is data that is the same for all measurements from a device (e.g., platform)
  - metadata consists of a list of fields
- measurement is the data that varies for each (type of) measurement
  - measurements consists of a list of paths

## Paths
- are used to differentiate between different types of measurements that might contain different fields
- right now we have instantaneous, duration, cumulative but they can be added as needed to group / categorize the data
```yaml
path: #path of the category (needs to be an array) [REQUIRED]
arrayMapAll: #whether all entries in the category should be mapped, alternatively index can be provided [REQUIRED] and [DEPRECATED] so only 'true' is supported
fields: #list of fields that are contained in the measurements of the category [REQUIRED]
```

## Fields
- field describes a field that should be mapped 
- 'field' has fields:
```yaml
name: # internal name of the field (only used inside the mapper) [REQUIRED]
source: # absolute path of the field inside the incoming json [REQUIRED]
value: #specified if one value should always be used for a field
transform: #specified if a transformation should be applied
# ONE OF source, transform or value is [REQUIRED]
target: #absolute path of the field inside the FHIR json [REQUIRED]
optional: #specifies if a field is optional [REQUIRED]
type: #specifies the type of the field [REQUIRED]
lineProtocol: # specifies the name of the field and the type
```

## Transform
- transform describes a transformation that should be applied to a field
- e.g., append, prepend, map, mapBasedOn, flatMap, substring, split
- note that not all of them are implemented yet

```yaml
type: #describes the tpe of transformation [REQUIRED]
params: #array of parameters that are passed to the transformation, they differ between transformations [REQUIRED]
```

## Mappings

```yaml
path: #specifies the path that the field should be set at, is used to find the correct mapping list for a transformation [REQUIRED]
basedOn: #specifies the field referenced by the key [REQUIRED]
valueType: # type of the value [REQUIRED]
map: #actual mappings [REQUIRED]
```

## Map
- a rule that specifies a `mapBasedOn` transformation
```yaml
key: #original value of the 'basedOn' field [REQUIRED]
value: #new value that should be set for the 'path' field [REQUIRED]
```

## LineProtocol

- Describes how the FHIR fields should be mapped to LineProtocol. The `type` field specifies the type of field.
  - 'measurement' must occur exactly once
  - 'timestamp' must occur exactly once
  - 'tag' may occur zero or more times
  - 'field' may occur one or more times
  - all other values set for that field will be ignored

```yaml
name: #describes the key in the line-protocol, ignored for measurement and timestamp [REQUIRED]
type: #the type of field in LP
```
