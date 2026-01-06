package org.example.config;

import org.apache.kafka.streams.StreamsConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.Properties;

public class KafkaConfig {

    private static final Logger log = LoggerFactory.getLogger(KafkaConfig.class);

    public static Properties getKafkaStreamsConfig() {

        // Read broker info from environment variable KAFKA_BROKER
        String envValue = Environment.KAFKA_BROKER_ENV_VAR;
        String partitionThreads = Environment.PARTITION_THREADS;

        String bootstrapServers;
        if (envValue == null || envValue.trim().isEmpty()) {
            // Fallback to sensible default
            bootstrapServers = "localhost:9092";
            log.warn("Env var '{}' not set. Using default bootstrap servers: {}", Environment.KAFKA_BROKER_ENV_VAR, bootstrapServers);
        } else {
            String trimmed = envValue.trim();
            // If the value already looks like a full bootstrap servers string (contains ':' or commas), use as-is
            if (trimmed.contains(":") || trimmed.contains(",")) {
                bootstrapServers = trimmed;
            } else {
                // Treat it as a host and append the default Kafka port
                bootstrapServers = trimmed + ":9092";
            }
            log.info("Using bootstrap servers from env '{}': {}", Environment.KAFKA_BROKER_ENV_VAR, bootstrapServers);
        }


        return setProperties(bootstrapServers);
    }

    private static Properties setProperties(String bootstrapServers) {
        Properties configurations = new Properties();

        configurations.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        configurations.put(StreamsConfig.APPLICATION_ID_CONFIG, Environment.APP_ID);
        configurations.put(StreamsConfig.NUM_STREAM_THREADS_CONFIG, Environment.PARTITION_THREADS);
        configurations.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG, org.apache.kafka.common.serialization.Serdes.String().getClass().getName());
        configurations.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG, org.apache.kafka.common.serialization.Serdes.String().getClass().getName());

        configurations.put(StreamsConfig.REQUEST_TIMEOUT_MS_CONFIG, "20000");
        configurations.put(StreamsConfig.RETRY_BACKOFF_MS_CONFIG, "500");
        return configurations;
    }

}
