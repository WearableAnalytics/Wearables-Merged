package org.example.config;

import org.example.fhir.model.MappingYaml;
import org.example.ConfigLoader;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Environment {

    private static final Logger log = LoggerFactory.getLogger(Environment.class);


    public static final String INPUT_TOPIC = setEnvWithDefault("INPUT_TOPIC", "wearables-raw");

    public static final String OUTPUT_TOPIC = setEnvWithDefault("OUTPUT_TOPIC", "wearables-lp");
    public static final String DLQ_TOPIC = setEnvWithDefault("DLQ_TOPIC", "dlq");

    public static final String KAFKA_BROKER_ENV_VAR = setEnvWithDefault("KAFKA_BROKER_ENV_VAR", "kafka-kafka-bootstrap:9092");
    public static final String NUM_STREAM_THREADS = setEnvWithDefault("NUM_STREAM_THREADS", "1");
    public static final int PARTITIONS = parseInt(setEnvWithDefault("PARTITIONS", "8"));
    public static final String APP_ID = setEnvWithDefault("APP_ID", "mapper-validator");
    public static final String MAPPING_YAML_PATH = setEnvWithDefault("MAPPING_YAML_PATH", "config/json-to-fhir-new.yaml");
    public static final int VALIDATION_FREQUENCY = parseInt(setEnvWithDefault("VALIDATION_FREQUENCY", "100"));

    public static final MappingYaml TEMPLATE = ConfigLoader.loadConfig(MAPPING_YAML_PATH, MappingYaml.class);

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

    private static int parseInt(String v) throws NumberFormatException{

        return Integer.parseInt(v);

    }

}
