package org.example;

import com.google.gson.JsonObject;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.stream.Stream;

import org.apache.kafka.common.protocol.types.Field;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Branched;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Named;
import org.example.config.Environment;
import org.example.config.KafkaConfig;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.fhir.model.MapReturn;
import org.example.lineprotocol.LineProtocolParser;
import org.hl7.fhir.r5.elementmodel.JsonParser;
import org.rocksdb.Env;
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

        //Map the incoming json to FHIR and validate it, when it returns an error we wrap it and push it to a DLQ
        KStream<String, String> output = rawJson.flatMapValues(value -> {

            //We save the valid FHIR JSONs grouped by their category to be able to make it impossible to map to LP with the wrong configuration
            Map<String, List<JsonObject>> validFhir = new HashMap<>();
            List<String> validLineProtocol = new ArrayList<>();
            //Grouping is not important for invalid measurement
            List<String> invalidFhir = new ArrayList<>();

            try {
                if (value == null || value.isBlank()) {
                    log.warn("Pushing empty payload to DLQ");
                    invalidFhir.add(dlqEmptyPayload());
                    //without any incoming data we dont have to continue
                    return invalidFhir;
                }

                Map<String, MapReturn> mr = Mapper.mapFhir(value);

                for (Map.Entry<String, MapReturn> e : mr.entrySet()) {

                    log.debug("inspecting batch {}", value);
                    inspectMappings(e.getKey(), e.getValue(), validFhir, invalidFhir);

                }

                LineProtocolParser lpParser = new LineProtocolParser();

                for (Map.Entry<String, List<JsonObject>> e : validFhir.entrySet()) {
                    e.getValue().forEach(v -> {
                        try {
                            String lpString = lpParser.parse(e.getKey(), v);
                            log.info(lpString);
                            validLineProtocol.add(lpString);

                        } catch (IllegalArgumentException iae) {
                            log.error("Line Protocol transformation failed", iae);

                            // wrap failed LP conversion into DLQ JSON
                            invalidFhir.add(dlq("Line Protocol transformation failed: " + iae.getMessage(), v.toString()));
                        } catch (Exception ex) {
                            log.error("Unexpected error during Line Protocol transformation", ex);

                            // catch-all DLQ wrapper
                            invalidFhir.add(dlq("Unexpected LP transformation error: " + ex.getMessage(), v.toString()));
                        }
                    });

                }

            } catch (Exception ex) {
                log.error("Failed to transform payload into FHIR, pushing problematic message to DLQ", ex);
                invalidFhir.add(dlq(ex.getMessage(), value));
            }

            //return the invalid FHIR as well as valid LineProtocol
            return Stream.concat(invalidFhir.stream(), validLineProtocol.stream()).toList();
        });

        Map<String, KStream<String, String>> branches = output.split(Named.as("res-"))
                .branch(((k, v) -> v.substring(0, 5).contains("{")), Branched.as("dlq")) //TODO improve this
                .defaultBranch(Branched.as("valid"));

        KStream<String, String> fhirDLQ = branches.get("res-dlq");
        KStream<String, String> lp = branches.get("res-valid");

        fhirDLQ.to(Environment.DLQ_TOPIC);
        lp.to(Environment.OUTPUT_TOPIC);

        runStreamsInstance(builder);
    }

    /***
     This function takes the measurements that are grouped by category and whether they were successfully mapped and tries to validate them. If validation was successful, they are added to the measurements that should be mapped to LP, if not, hey are formatted as string to be written to the DLQ.
     * @param category the category of the measurement in the raw JSON
     * @param mr the object that holds the successful and unsuccessful mappings separately for each category.
     * @param validFhir the FHIR JSONs that should be mapped to LP
     * @param invalidFhir the invalid FHIR JSONs that should be written to the DLQ
     */
    private static void inspectMappings(
            String category,
            MapReturn mr,
            Map<String, List<JsonObject>> validFhir,
            List<String> invalidFhir) {

        boolean onlyValid = true;

        if (mr.getValid() != null) {
            for (JsonObject obj : mr.getValid()) {
                String json = obj.toString();

                if (Validator.validateFhir(json)) {
                    validFhir.computeIfAbsent(category, k -> new ArrayList<>());
                    validFhir.get(category).add(obj);
                } else {
                    onlyValid = false;
                    String s = dlq("Failed FHIR validation", json);
                    log.warn("Got invalid measurement during validation: {}", s);
                    invalidFhir.add(s);
                }
            }
        } else {
            onlyValid = false;
            log.error("Measurement batch contained no valid measurement");
        }

        if (mr.getInvalid() != null) {
            // INVALID FROM MAPPER
            for (JsonObject obj : mr.getInvalid()) {
                String s = dlq(
                        "Problem occurred during mapping, check logs for more information",
                        obj.toString()
                );
                log.warn("Got invalid measurement during mapping: {}", s);
                invalidFhir.add(s);
            }
        } else {
            log.debug("Measurement batch contained no invalid measurements");
        }

        if (onlyValid) log.debug("Measurement batch contained only valid measurements");
    }

    private static void runStreamsInstance(StreamsBuilder builder) throws InterruptedException {
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

    private static String dlq(String error, String payload) {
        return """
                {
                    "valid": false,
                    "error": "%s",
                    "payload": %s
                }
                """.formatted(
                escape(error),
                payload == null ? "null" : "\"" + escape(payload) + "\""
        ).trim();
    }

    private static String dlqEmptyPayload() {
        return """
                {
                    "valid": false,
                    "error": "Empty payload",
                    "payload": null
                }
                """.trim();
    }

    private static String escape(String s) {
        return s == null ? null : s.replace("\"", "\\\"");
    }

}

