package org.example;

import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
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
        KStream<String, String> fhirJson = rawJson.flatMapValues(value -> {
            List<String> outputs = new ArrayList<>();

            try {
                if (value == null || value.isBlank()) {
                    log.warn("Pushing empty payload to DLQ");
                    outputs.add(dlqEmptyPayload());
                    return outputs;
                }

                boolean onlyValid = true;

                MapReturn mr = Mapper.mapFhir(value);

                // VALID FHIR
                if (mr.getValid() != null) {
                    for (JsonObject obj : mr.getValid()) {
                        String json = obj.toString();

                        if (Validator.validateFhir(json)) {
                            outputs.add(json);
                        } else {
                            onlyValid = false;
                            String s = dlq("Failed FHIR validation", json);
                            log.warn("Got invalid measurement during validation: {}", s);
                            outputs.add(s);
                        }
                    }
                } else {
                    onlyValid = false;
                    log.error("Measurement batch contained no valid measurements: {}", value);
                }

                if (mr.getInvalid() != null) {
                    // INVALID FROM MAPPER
                    for (JsonObject obj : mr.getInvalid()) {
                        String s = dlq(
                                "Problem occurred during mapping, check logs for more information",
                                obj.toString()
                        );
                        log.warn("Got invalid measurement during mapping: {}", s);
                        outputs.add(s);
                    }
                } else {
                    log.debug("Measurement batch contained no invalid measurements: {}", value);
                }

                if (onlyValid) log.debug("Measurement batch contained only valid measurements");


            } catch (Exception ex) {
                log.error("Failed to transform payload into FHIR, pushing problematic message to DLQ", ex);
                outputs.add(dlq(ex.getMessage(), value));
            }

            return outputs;
        });

        KStream<String, String> valid = splitAndWriteFHIR(fhirJson);

        // Apply the second part of the mapping so the data is in InfluxDB Line Protocol and we can write it to influx
        LineProtocolParser lpParser = new LineProtocolParser();

        //Parse the valid fhir entries to LP
        KStream<String, String> influxLp = valid.mapValues(str -> {
            try {
                log.info("Received FHIR payload: {}", str);
                String lpString = lpParser.parse(str);
                log.info(lpString);
                return lpString;
            } catch (IllegalArgumentException iae) {
                log.error("Line Protocol transformation failed", iae);

                // wrap failed LP conversion into DLQ JSON
                return dlq("Line Protocol transformation failed: " + iae.getMessage(), str);
            } catch (Exception ex) {
                log.error("Unexpected error during Line Protocol transformation", ex);

                // catch-all DLQ wrapper
                return dlq("Unexpected LP transformation error: " + ex.getMessage(), str);
            }
        });

        splitAndWriteLP(influxLp);

        runStreamsInstance(builder);
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

    private static void splitAndWriteLP(KStream<String, String> influxLp) {
        //split the lp results into valid and invalid values
        var lpBranches = influxLp.split(Named.as("lp-"))
                .branch((k, v) -> !v.substring(0, 15).contains("valid"), Branched.as("valid"))
                .defaultBranch(Branched.as("invalid"));

        KStream<String, String> lpValid = lpBranches.get("lp-valid");
        KStream<String, String> lpInvalid = lpBranches.get("lp-invalid");

        //write them to the corresponding topics
        lpValid.to(Environment.LP_OUTPUT_TOPIC);
        lpInvalid.to(Environment.LP_DLQ_TOPIC);
    }

    private static KStream<String, String> splitAndWriteFHIR(KStream<String, String> fhirJson) {
        //split the Stream into valid and invalid entries
        Map<String, KStream<String, String>> branched = fhirJson.split(Named.as("fhir-"))
                .branch((k, v) -> !v.substring(0, 15).contains("valid"), Branched.as("valid"))
                .defaultBranch(Branched.as("invalid"));

        branched.forEach((key, value) -> System.out.println(key));

        KStream<String, String> valid = branched.get("fhir-valid");
        KStream<String, String> invalid = branched.get("fhir-invalid");

        //Write the FHIR JSON to one topic so it can be written to blob storage / iceberg / whatever
        valid.to(Environment.FHIR_OUTPUT_TOPIC);

        //write invalid to DLQ
        invalid.to(Environment.FHIR_DLQ_TOPIC);

        return valid;
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

