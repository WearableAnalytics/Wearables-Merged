package org.example;

import com.google.gson.*;
import org.apache.jena.base.Sys;
import org.apache.kafka.common.protocol.types.Field;
import org.example.config.Environment;
import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.fhir.model.MapReturn;
import org.example.fhir.model.MappingYaml;
import org.example.lineprotocol.LineProtocolParser;
import org.javatuples.Pair;
import org.junit.Test;
import org.junit.jupiter.api.DisplayName;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.FileWriter;
import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.*;

public class FhirMapperTest {

    private static final Logger log = LoggerFactory.getLogger(FhirMapperTest.class);

    @Test
    @DisplayName("Map incoming iOS json to fhir")
    public void mappingTest() throws IOException, URISyntaxException {

        MappingYaml yaml = ConfigLoader.loadConfig("./config/mapping-2026-01-28.yaml", MappingYaml.class);
        yaml.validate();

        Validator.initiliazeFhirValidator(100);
        int validationCounter = 0;

        Mapper mapper = new Mapper(yaml, 100);
        LineProtocolParser lpParser = new LineProtocolParser(yaml);

        DependencyGraph g = new DependencyGraph(yaml);

        g.createGraphBase();
        g.enrichGraphWithFhir();
        Map<String, Set<Node>> graphs = g.build();

        Path path = Paths.get(
                getClass().getClassLoader().getResource("sample.json").toURI()
        );
        String input = Files.readString(path);

        List<String> flattened = mapper.flatMapJson(input);

        log.info("flattened has length {}", flattened.size());

        for (String s : flattened) {

            Pair<String, JsonObject> categoryFhirTuple = null;
            try {
                categoryFhirTuple = mapper.mapFhir(s);
            } catch (RuntimeException e) {
                log.error("Mapping failed", e);
                continue;
            }

            log.info("MAPPED");

            JsonObject fhir = categoryFhirTuple.getValue1();
            String category = categoryFhirTuple.getValue0();

            if (category == null || fhir == null) {
                log.warn("Category or fhir is null");
                continue;
            }

            try {
                validationCounter = Validator.validateFhir(fhir, validationCounter);
            } catch (IllegalArgumentException iae) {
                log.warn("fhir validation failed with exception: {}", iae.getMessage());
                continue;
            }

            try {
                Files.write(
                        Paths.get("outputs/fhir/all_fhir.txt"),
                        List.of(fhir.toString()),
                        StandardOpenOption.CREATE,
                        StandardOpenOption.APPEND
                );
            } catch (IOException io) {
                log.error("Failed to append FHIR output", io);
            }

            String lpString = null;

            try {
                Set<Node> fittingBase = graphs.get(category);
                lpString = lpParser.parse(category, fhir, fittingBase);
                log.info(lpString);

            } catch (IllegalArgumentException iae) {
                log.error("Line Protocol transformation failed", iae);

                try {
                    if (lpString != null) {
                        Files.write(
                                Paths.get("outputs/lp/invalid_lp.txt"),
                                List.of(lpString),
                                StandardOpenOption.CREATE,
                                StandardOpenOption.APPEND
                        );
                    }
                } catch (IOException io) {
                    log.error("Failed to append FHIR output", io);
                }

            } catch (Exception ex) {
                log.error("Unexpected error during Line Protocol transformation", ex);

                try {
                    if (lpString != null) {
                        Files.write(
                                Paths.get("outputs/lp/invalid_lp.txt"),
                                List.of(lpString),
                                StandardOpenOption.CREATE,
                                StandardOpenOption.APPEND
                        );
                    }
                } catch (IOException io) {
                    log.error("Failed to append FHIR output", io);
                }
            }

            try {
                if (lpString != null) {
                    Files.write(
                            Paths.get("outputs/lp/valid_lp.txt"),
                            List.of(lpString),
                            StandardOpenOption.CREATE,
                            StandardOpenOption.APPEND
                    );
                }
            } catch (IOException io) {
                log.error("Failed to append FHIR output", io);
            }


        }

//        Pair<String, JsonObject> results = mapper.mapFhir(input);
//
//        for (Map.Entry<String, MapReturn> entry : results.entrySet()) {
//
//            log.info("Entries found for {}", entry.getKey());
//
//            JsonArray mappedFhir = new JsonArray();
//            JsonArray mappedFhirError = new JsonArray();
//            int good = 0;
//            int bad = 0;
//
//            for (JsonObject r : entry.getValue().getValid()){
//                boolean res = Validator.validateFhir(r.toString());
//                if (res) {
//                    mappedFhir.add(r);
//                    good++;
//                } else {
//                    mappedFhirError.add(r);
//                    bad++;
//                }
//            }
//
//            log.info("Good: {} | Bad: {}", good, bad);
//
//            for (JsonElement e : entry.getValue().getInvalid()) {
//                mappedFhirError.add(e);
//            }
//
//            Gson gson = new Gson();
//
//            Files.write(
//                    Paths.get(String.format("outputs/fhir/%s.valid.json", entry.getKey())),
//                    gson.toJson(mappedFhir).getBytes()
//            );
//
//            Files.write(
//                    Paths.get(String.format("outputs/fhir/%s.invalid.json", entry.getKey())),
//                    gson.toJson(mappedFhirError).getBytes()
//            );
//
//            List<String> lpRes = new ArrayList<>();
//
//            LineProtocolParser lpParser = new LineProtocolParser();
//            for (Iterator<JsonElement> it = mappedFhir.iterator(); it.hasNext();) {
//                JsonObject r = it.next().getAsJsonObject();
//                try {
//                    String res = lpParser.parse(entry.getKey(), r, graphs.get(entry.getKey()), yaml);
//                    lpRes.add(res);
//                } catch (IllegalArgumentException iae){
//                    log.warn("LP parse failed: {}", iae.getMessage());
//                 }
//
//            }
//
//            Files.write(
//                    Paths.get(String.format("outputs/lp/%s.valid.txt", entry.getKey())),
//                    lpRes
//            );
//        }

    }
}
