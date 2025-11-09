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
7. Write the test.json message to "raw" kafka topic, it should get mapped and written to the "fhri" topic