package org.example;

import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.KStream;
import org.example.config.Environment;
import org.example.config.KafkaConfig;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.lineprotocol.LineProtocolParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


public class Main {

    // Testing: This is a change that should trigger the Workflow


    private static final Logger log = LoggerFactory.getLogger(Main.class);

    public static void main(String[] args) throws InterruptedException {

        log.debug("Using slf4j for logging");

        Validator.initiliazeFhirValidator();

        StreamsBuilder builder = new StreamsBuilder();

        //Define an input topic: Raw JSON from providers
        KStream<String, String> rawJson = builder.stream(Environment.INPUT_TOPIC);

        KStream<String, String> fhirJson = rawJson.flatMapValues(value -> {
            List<String> outputs = new ArrayList<>();
            try {
                if (value == null || value.isBlank()) {
                    log.warn("Skipping empty payload");
                    return outputs;
                }
                List<JsonObject> mapped = Mapper.mapFhir(value);
                for (JsonObject obj : mapped) {
                    String json = obj.toString();
                    if (Validator.validateFhir(json)) {
                        outputs.add(json);
                    } else {
                        log.warn("Skipping invalid FHIR observation");
                    }
                }
            } catch (Exception ex) {
                log.error("Failed to transform payload into FHIR", ex);
            }
            return outputs;
        });

        //Write the FHIR JSON to one topic so it can be written to blob storage / iceberg / whatever
        fhirJson.to(Environment.FHIR_OUTPUT_TOPIC);

        // Apply the second part of the mapping so the data is in InfluxDB Line Protocol and we can write it to influx
        LineProtocolParser lpParser = new LineProtocolParser();
        KStream<String, String> influxLp = fhirJson.mapValues(str -> {
            try {
                log.debug("Received fhir payload: {}", str);
                return lpParser.parse(str);
            } catch (IllegalArgumentException iae) {
                log.error("Line Protocol tranformation failed with exception", iae);
                return "";
            }
        });

        influxLp.to(Environment.LP_OUTPUT_TOPIC);

        Topology topology = builder.build();
        KafkaStreams streamsApp = new KafkaStreams(topology, KafkaConfig.getKafkaStreamsConfig());
        streamsApp.start();
        log.info("Kafka Streams application '{}' started. Topology description:\n{}", Environment.APP_ID, topology.describe());

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            log.info("Shutdown signal received. Closing Kafka Streams application '{}'...", Environment.APP_ID);
            streamsApp.close();
            log.info("Kafka Streams application '{}' closed.", Environment.APP_ID);
        }));
        new CountDownLatch(1).await();
    }

}
