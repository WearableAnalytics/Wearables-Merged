package org.example;

import com.google.gson.*;
import org.apache.kafka.common.protocol.types.Field;
import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.fhir.model.MapReturn;
import org.example.fhir.model.MappingYaml;
import org.example.lineprotocol.LineProtocolParser;
import org.junit.Test;
import org.junit.jupiter.api.DisplayName;

import java.io.FileWriter;
import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.*;

public class FhirMapperTest {

    @Test
    @DisplayName("Map incoming iOS json to fhir")
    public void mappingTest() throws IOException, URISyntaxException {

        MappingYaml yaml = ConfigLoader.loadConfig("./config/mapping-2026-01-28.yaml", MappingYaml.class);
        yaml.validate();

        Validator.initiliazeFhirValidator();
        Mapper mapper = new Mapper(yaml);

        DependencyGraph g = new DependencyGraph(yaml);

        g.createGraphBase();
        g.enrichGraphWithFhir();
        Map<String, Set<Node>> graphs = g.build();

        Path path = Paths.get(
                getClass().getClassLoader().getResource("sample.json").toURI()
        );
        String input = Files.readString(path);

        Map<String, MapReturn> results = mapper.mapFhir(input);

        for (Map.Entry<String, MapReturn> entry : results.entrySet()) {

            System.out.printf("Entries found for %s \n", entry.getKey());

            JsonArray mappedFhir = new JsonArray();
            JsonArray mappedFhirError = new JsonArray();
            int good = 0;
            int bad = 0;

            for (JsonObject r : entry.getValue().getValid()){
                boolean res = Validator.validateFhir(r.toString());
                if (res) {
                    mappedFhir.add(r);
                    good++;
                } else {
                    mappedFhirError.add(r);
                    bad++;
                }
            }

            System.out.printf("Good: %s \n Bad: %s \n", good, bad);

            for (JsonElement e : entry.getValue().getInvalid()) {
                mappedFhirError.add(e);
            }

            Gson gson = new Gson();

            Files.write(
                    Paths.get(String.format("outputs/fhir/%s.valid.json", entry.getKey())),
                    gson.toJson(mappedFhir).getBytes()
            );

            Files.write(
                    Paths.get(String.format("outputs/fhir/%s.invalid.json", entry.getKey())),
                    gson.toJson(mappedFhirError).getBytes()
            );

            List<String> lpRes = new ArrayList<>();

            LineProtocolParser lpParser = new LineProtocolParser();
            for (Iterator<JsonElement> it = mappedFhir.iterator(); it.hasNext();) {
                JsonObject r = it.next().getAsJsonObject();
                try {
                    String res = lpParser.parse(entry.getKey(), r, graphs.get(entry.getKey()), yaml);
                    lpRes.add(res);
                } catch (IllegalArgumentException iae){
                    System.out.println(iae.getMessage());
                }

            }

            Files.write(
                    Paths.get(String.format("outputs/lp/%s.valid.txt", entry.getKey())),
                    lpRes
            );


        }

    }
}
