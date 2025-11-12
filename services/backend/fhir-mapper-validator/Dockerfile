FROM eclipse-temurin:17-jdk

WORKDIR /app

# Copy the shaded JAR that includes all dependencies (ensures SLF4J binding is present)
ARG JAR_FILE=target/*-shaded.jar
COPY ${JAR_FILE} /app/app.jar

# Ensure the log directory exists for Logback FileAppender
RUN mkdir -p /app/logs

# Optional: provide a default external YAML; can be overridden by a mounted file at runtime
COPY src/main/resources/json-to-fhir.yaml /config/mapping.yaml
COPY src/main/resources/fhir-to-lineprotocol.yaml /config/fhir-to-lineprotocol.yaml

# Configure the app
ENV MAPPING_YAML_PATH="/config/mapping.yaml"
ENV FHIR_LP_MAPPING_YAML_PATH="/config/fhir-to-lineprotocol.yaml"

ENV INPUT_TOPIC="wearables-raw"
ENV FHIR_OUTPUT_TOPIC="wearables-fhir"
ENV LP_OUTPUT_TOPIC="wearables-lp"
ENV KAFKA_BROKER_ENV_VAR="my-cluster-kafka-bootstrap:9092"
ENV APP_ID="mapper-validator"

ENTRYPOINT ["java", "-Xmx3500m", "-jar", "/app/app.jar"]