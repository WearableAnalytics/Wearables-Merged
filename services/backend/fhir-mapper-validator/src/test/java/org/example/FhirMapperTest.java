package org.example;

import com.google.gson.JsonObject;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.lineprotocol.LineProtocolParser;
import org.junit.Test;
import org.junit.jupiter.api.DisplayName;
import com.google.gson.Gson;
import com.google.gson.GsonBuilder;

import java.io.FileWriter;
import java.io.IOException;
import java.net.URISyntaxException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class FhirMapperTest {

    @Test
    @DisplayName("Map incoming iOS json to fhir")
    public void mappingTest() throws IOException, URISyntaxException {

        Validator.initiliazeFhirValidator();

        Path path = Paths.get(
                getClass().getClassLoader().getResource("input.json").toURI()
        );
        String input = Files.readString(path);

        List<JsonObject> results = Mapper.mapFhir(input);

        if (results.size() <= 1){
            throw new RuntimeException("there should be more than one element here");
        }

        System.out.println(results.size());

        for (JsonObject r : results){
            System.out.println(r.toString());
            boolean res = Validator.validateFhir(r.toString());
            if (!res) throw new RuntimeException("cant parse");
        }

        Gson gson = new GsonBuilder().setPrettyPrinting().create();

        try (FileWriter writer = new FileWriter("output.json")) {
            gson.toJson(results, writer);  // writes the whole list as formatted JSON
        }

        List<String> lpRes = new ArrayList<>();

        LineProtocolParser lpParser = new LineProtocolParser();
        for (JsonObject r : results){
            String res = lpParser.parse(r.toString());
            lpRes.add(res);
        }

        Files.write(Paths.get("output-lp.txt"), lpRes);

    }
}
