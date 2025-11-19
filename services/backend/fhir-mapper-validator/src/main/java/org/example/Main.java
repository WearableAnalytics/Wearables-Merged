package org.example;

import org.example.config.Environment;
import org.example.config.KafkaConfig;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.lineprotocol.LineProtocolParser;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import java.util.concurrent.CountDownLatch;
import com.google.gson.*;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.ValueMapper;


public class Main {

    // Testing: This is a change that should trigger the Workflow


    private static final Logger log = LoggerFactory.getLogger(Main.class);

    public static void main(String[] args) throws InterruptedException {

        log.debug("Using slf4j for logging");

        Validator.initiliazeFhirValidator();

        StreamsBuilder builder = new StreamsBuilder();

        //Define an input topic: Raw JSON from providers
        KStream<String, String> rawJson = builder.stream(Environment.INPUT_TOPIC);

        //Define the first part of the mapping: Raw JSON to FHIR JSON
        KStream<String, String> fhirJson = rawJson.mapValues(new ValueMapper<String, String>() {
            @Override
            public String apply(String str) {
                try {
                    log.debug("Received message payload: {}", str);

                    JsonObject output = Mapper.mapFhir(str);

                    //TODO: dead letter queue?
                    if (output == null) return "";

                    String outStr = output.toString();
                    log.debug("Produced mapped payload: {}", outStr);

                    if (Validator.validateFhir(outStr)) {
                        return outStr;
                    } else {
                        //TODO DLQ??
                        return "";
                    }

                } catch (Exception ex) {
                    log.error("Fhir transformation failed with exception", ex);
                    //TODO DLQ??
                    return "";
                }
            }
        });

        //Write the FHIR JSON to one topic so it can be written to blob storage / iceberg / whatever
        fhirJson.to(Environment.FHIR_OUTPUT_TOPIC);

        // Apply the second part of the mapping so the data is in InfluxDB Line Protocol and we can write it to influx
        KStream<String, String> influxLp = fhirJson.mapValues(new ValueMapper<String, String>() {
            @Override
            public String apply(String str) {
                try {
                    log.debug("Received fhir payload: {}", str);

                    LineProtocolParser lpParser = new LineProtocolParser();

                    return lpParser.parse(str);
                }catch(IllegalArgumentException iae){
                    log.error("Line Protocol tranformation failed with exception", iae);
                    return "";
                }
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

