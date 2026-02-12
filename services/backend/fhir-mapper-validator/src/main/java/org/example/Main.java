package org.example;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.CountDownLatch;
import java.util.stream.Stream;

import com.google.gson.JsonParser;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.common.utils.Utils;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.Branched;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.Named;
import org.apache.kafka.streams.kstream.Repartitioned;
import org.example.config.Environment;
import org.example.config.KafkaConfig;
import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.fhir.model.MapReturn;
import org.example.lineprotocol.LineProtocolParser;
import org.javatuples.Pair;
import org.rocksdb.Env;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


public class Main {

    private static final Logger log = LoggerFactory.getLogger(Main.class);

    public static void main(String[] args) throws InterruptedException {

        log.debug("Using slf4j for logging");

        Validator.initiliazeFhirValidator(100);
        Mapper mapper = new Mapper(Environment.TEMPLATE, Environment.VALIDATION_FREQUENCY);

        DependencyGraph dependencyGraph = new DependencyGraph(Environment.TEMPLATE);

        //This will build the dependency graph derived from the Mapping YAML
        dependencyGraph.createGraphBase();
        dependencyGraph.enrichGraphWithFhir();

        //the map maps from the category name (e.g., instantaneous, duration, etc.) to the minimal set of nodes needed to derive the rest of the fhir
        Map<String, Set<Node>> categoryGraphs = dependencyGraph.build();

        try {
            Environment.TEMPLATE.validate();
        } catch (IllegalArgumentException iae) {
            log.error("There was an error verifying the mapping schema: {}", iae.getMessage());
            return;
        }

        StreamsBuilder builder = new StreamsBuilder();

        //Define an input topic: Raw JSON from providers
        KStream<String, String> rawJson = builder.stream(Environment.INPUT_TOPIC);

        KStream<String, String> flattened = rawJson.flatMapValues(mapper::flatMapJson);

        KStream<String, String> rekeyed = flattened.selectKey((oldKey, value) -> parallelKey(value));

        KStream<String, String> repartitioned = rekeyed.repartition(
                Repartitioned.with(Serdes.String(), Serdes.String())
                        .withNumberOfPartitions(Environment.PARTITIONS)  //taken from env and should be the same as the actual partitions of the raw Topic in the cluster partitions in the cluster
                        .withName("flat-repartition")
        );

        //Map the incoming json to FHIR and validate it, when it returns an error we wrap it and push it to a DLQ
        KStream<String, String> output = repartitioned.mapValues(value -> mapper.mapAndValidate(value, categoryGraphs));

        Map<String, KStream<String, String>> branches = output.split(Named.as("res-"))
                .branch((k, v) -> v != null && !v.substring(0, 5).contains("{"), Branched.as("valid"))
                .defaultBranch(Branched.as("dlq"));

        KStream<String, String> fhirDLQ = branches.get("res-dlq");
        KStream<String, String> lp = branches.get("res-valid");

        fhirDLQ.to(Environment.DLQ_TOPIC);
        lp.to(Environment.OUTPUT_TOPIC);

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

    private static String parallelKey(String value) {
        int hash = Utils.murmur2(value.getBytes(StandardCharsets.UTF_8));
        return Integer.toUnsignedString(hash);
    }

}

