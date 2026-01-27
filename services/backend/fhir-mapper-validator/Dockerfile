FROM maven:3.9.3-eclipse-temurin-20 AS build
WORKDIR /app

# Copy source code
COPY pom.xml .
COPY src ./src

# Build the JAR
RUN mvn clean package -DskipTests

FROM eclipse-temurin:17-jdk

WORKDIR /app

# Copy the shaded JAR that includes all dependencies (ensures SLF4J binding is present)
COPY --from=build  /app/target/mapper-validator-1.0-SNAPSHOT-shaded.jar /app/app.jar

# Ensure the log directory exists for Logback FileAppender
RUN mkdir -p /app/logs

# Optional: provide a default external YAML; can be overridden by a mounted file at runtime
COPY src/main/resources/json-to-fhir-new.yaml /config/mapping.yaml

# Environment variables are set through k8s

ENTRYPOINT ["java", "-Xmx3500m", "-jar", "/app/app.jar"]