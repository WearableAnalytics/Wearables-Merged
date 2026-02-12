package org.example;

import org.apache.kafka.common.serialization.Serde;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.*;
import org.apache.kafka.streams.processor.api.Processor;
import org.apache.kafka.streams.processor.api.ProcessorContext;
import org.apache.kafka.streams.processor.api.ProcessorSupplier;
import org.apache.kafka.streams.processor.api.Record;
import org.apache.kafka.streams.state.KeyValueStore;
import org.apache.kafka.streams.state.Stores;
import org.apache.kafka.streams.test.TestRecord;
import org.example.fhir.model.MappingYaml;
import org.junit.Before;
import org.junit.Test;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.List;
import java.util.Properties;
import java.util.concurrent.Flow;


public class E2ETest {

    private static final Logger log = LoggerFactory.getLogger(E2ETest.class);

    private TopologyTestDriver testDriver;
    private TestInputTopic<String, String> inputTopic;
    private TestOutputTopic<String, String> outputTopic;
    private TestOutputTopic<String, String> dlqTopic;

    private final String mapperProcessorName = "mapper";
    private final String flatMapperProcessorName = "flatMapper";

    private final String inputTopicName = "input";
    private final String outputTopicName = "output";
    private final String dlqTopicName = "dlq";

    private final int validationFrq = 100;

    private Serde<String> stringSerde = new Serdes.StringSerde();

    @Before
    public void setup(){

        MappingYaml yaml = ConfigLoader.loadConfig("./config/mapping-2026-01-28.yaml", MappingYaml.class);
        yaml.validate();

        Topology topology = new Topology();
        topology.addSource("sourceProcessor", Serdes.String().deserializer(), Serdes.String().deserializer(), inputTopicName);
        topology.addProcessor(flatMapperProcessorName, new FlatMapperMockSupplier(yaml, validationFrq), "sourceProcessor");
        topology.addProcessor(mapperProcessorName, new MapperMockSupplier(yaml, validationFrq), flatMapperProcessorName);
        topology.addSink("sinkProcessor", outputTopicName, Serdes.String().serializer(), Serdes.String().serializer(), mapperProcessorName);
        topology.addSink("dlqProcessor", dlqTopicName, Serdes.String().serializer(), Serdes.String().serializer(), mapperProcessorName);

        // setup test driver
        Properties props = new Properties();
        props.setProperty(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG, Serdes.String().getClass().getName());
        props.setProperty(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG, Serdes.String().getClass().getName());
        testDriver = new TopologyTestDriver(topology, props);

        // setup test topics
        inputTopic = testDriver.createInputTopic(inputTopicName, stringSerde.serializer(), stringSerde.serializer());
        outputTopic = testDriver.createOutputTopic(outputTopicName, stringSerde.deserializer(), stringSerde.deserializer());
        dlqTopic = testDriver.createOutputTopic(dlqTopicName, stringSerde.deserializer(), stringSerde.deserializer());

    }

    @Test
    public void testAll() throws IOException, URISyntaxException {

        Path path = Paths.get(
                getClass().getClassLoader().getResource("sample.json").toURI()
        );
        String input = Files.readString(path);

        inputTopic.pipeInput(new TestRecord<>(input));

        List<String> results = outputTopic.readValuesToList();
        List<String> dlqMsgs = dlqTopic.readValuesToList();

        log.info("Valid: {}", results.size());
        log.info("Invalid: {}", dlqMsgs.size());

        try {
            if (!results.isEmpty()){
                Files.write(
                        Paths.get("outputs/e2e/output_valid.txt"),
                        results,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND
                );
            }

            if (!dlqMsgs.isEmpty()){
                Files.write(
                        Paths.get("outputs/e2e/output_invalid.txt"),
                        results,
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND
                );
            }
        } catch (IOException io) {
            log.error("Error when writing to file");
        }

    }


}


