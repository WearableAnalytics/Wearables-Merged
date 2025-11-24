package org.example.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Environment {

    private static final Logger log = LoggerFactory.getLogger(Environment.class);


    public static final String INPUT_TOPIC = setEnvWithDefault("INPUT_TOPIC", "wearables-raw");
    public static final String FHIR_OUTPUT_TOPIC = setEnvWithDefault("FHIR_OUTPUT_TOPIC", "wearables-fhir");
    public static final String LP_OUTPUT_TOPIC = setEnvWithDefault("LP_OUTPUT_TOPIC", "wearables-lp");
    public static final String KAFKA_BROKER_ENV_VAR = setEnvWithDefault("KAFKA_BROKER_ENV_VAR", "kafka-kafka-bootstrap:9092");
    public static final String APP_ID = setEnvWithDefault("APP_ID", "mapper-validator");
    public static final String MAPPING_YAML_PATH = setEnvWithDefault("MAPPING_YAML_PATH", "src/main/resources/test.yaml");
    public static final String FHIR_LP_MAPPING_YAML_PATH = setEnvWithDefault("FHIR_LP_MAPPING_YAML_PATH", "/config/fhir-to-lineprotocol.yaml");

    private static String setEnvWithDefault(String value, String defaultValue){
        String env = System.getenv(value);
        if (env != null) {
            log.debug("Found environment variable for {}", value);
            return env;
        } else {
            log.warn("Could not find environment variable for {}, using default {}", value, defaultValue);
            return defaultValue;
        }
    }

}
