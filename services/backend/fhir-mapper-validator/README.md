# Protoype for Mapping and Validation

- This is the proof-of-concept implementation I did of the mapping and validation logic running inside Kafka Streams
- It's written in Java for the provided libraries but most importantly because Kafka Streams only support Java
- PLEASE KEEP IN MIND that in its current state it's just a proof of concept, so the mapping logic and validation are just to show it works and in no way production ready

# What does it do?

- Kafka Streams instance reads from the "raw" topic
- Takes the input and uses the yaml file map the "source" field to the "target" field
- in doing so a FHIR json is automatically generated
- When all fields are inserted into the json, it is validated using the FHIR library
- If validation is successful, the result is written to the "fhir" topic

# Configure via YAML (state: 28.11.2025)

## Metadata and Measurements
- metadata is data that is the same for all measurements from a device (e.g., platform)
  - metadata consists of a list of fields
- measurement is the data that varies for each (type of) measurement
  - measurements consists of a list of paths

## Paths
- are used to differentiate between different types of measurements that might contain different fields
- right now we have instantaneous, duration, cumulative
```yaml
path: #path of the category (needs to be an array) [REQUIRED]
arrayMapAll: #whether all entries in the category should be mapped, alternatively index can be provided [REQUIRED]
fields: #list of fields that are contained in the measurements of the category [REQUIRED]
```

## Fields
- field describes a field that should be mapped 
- 'field' has fields:
```yaml
name: # internal name of the field (only used inside the mapper) [REQUIRED]
source: # absolute path of the field inside the incoming json [REQUIRED]
mapping: #specified whether a mapping rule should be applied
value: #specified if one value should always be used for a field
# ONE OF source, mapping or value is [REQUIRED]
target: #absolute path of the field inside the FHIR json [REQUIRED]
optional: #specifies if a field is optional [REQUIRED]
type: #specifies the type of the field [REQUIRED]
```

## Mapping
- mappings define mapping rules for the value in the specified path
- e.g., if you find KEY, map to VALUE

```yaml
path: #path of the FHIR field that should be mapped [REQUIRED]
basedOn: #path of the value that the mapping should be based on [REQUIRED]
valueType: #the type of the resulting new value [REQUIRED]
map: #list of mapping rules (see Map) [REQUIRED]
```

## Map
- a rule that specifies a mapping
```yaml
key: #original value of the 'basedOn' field [REQUIRED]
value: #new value that should be set for the 'path' field [REQUIRED]
```


# Setup

1. Run Minikube 
   1. Install minikube
   2. Start the cluster
2. Install the strimzi cluster operator
3. Run a default kafka configuration (you dont have to modify the default values / config)
4. Create a topic called kafka
5. Create kafka-topics: wearables-raw and wearables-fhir
6. Run the just-command
   1. Install just command runner (its worth it trust me)
   2. Run the command
7. Write the test.json message to "raw" kafka topic, it should get mapped and written to the "fhir" topic