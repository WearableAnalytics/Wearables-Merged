FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app

# Copy source code
COPY pom.xml .
COPY src ./src
COPY config ./config

# Build the JAR
RUN mvn -B -ntp package

FROM eclipse-temurin:17-jdk

WORKDIR /app

# Copy the shaded JAR that includes all dependencies (ensures SLF4J binding is present)
COPY --from=build  /app/target/mapper-validator-1.0-SNAPSHOT-shaded.jar /app/app.jar

# Ensure the log directory exists for Logback FileAppender
RUN mkdir -p /app/logs

# Optional: provide a default external YAML; can be overridden by a mounted file at runtime
COPY src/main/resources/mapping-2026-01-28.yaml /config/mapping.yaml

# Allow configurable log level at build time; defaults to INFO
ARG LOG_LEVEL=INFO
ENV LOG_LEVEL=${LOG_LEVEL}
ENV JAVA_TOOL_OPTIONS="-Xmx3500m"

# Environment variables are set through k8s

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
