package org.example;

import com.google.gson.JsonParser;
import org.example.lineprotocol.LineProtocolParser;
import org.junit.Test;
import org.junit.jupiter.api.DisplayName;

import static org.junit.jupiter.api.Assertions.*;

public class LineProtocolParserTest {

    private final LineProtocolParser parser = new LineProtocolParser();

    private static final String SAMPLE_OBS = """
            {
              "resourceType" : "Observation",
              "id" : "heart-rate",
              "meta" : {
                "profile" : ["http://hl7.org/fhir/StructureDefinition/vitalsigns"]
              },
              "text" : {
                "status" : "generated",
                "div" : "<div xmlns=\"http://www.w3.org/1999/xhtml\">...</div>"
              },
              "status" : "final",
              "category" : [{
                "coding" : [{
                  "system" : "http://terminology.hl7.org/CodeSystem/observation-category",
                  "code" : "vital-signs",
                  "display" : "Vital Signs"
                }],
                "text" : "Vital Signs"
              }],
              "code" : {
                "coding" : [{
                  "system" : "http://loinc.org",
                  "code" : "8867-4",
                  "display" : "Heart rate"
                }],
                "text" : "Heart rate"
              },
              "subject" : {
                "reference" : "Patient/example"
              },
              "effectiveDateTime" : "1762767194",
              "valueQuantity" : {
                "value" : 44,
                "unit" : "beats/minute",
                "system" : "http://unitsofmeasure.org",
                "code" : "/min"
              }
            }
            """;
}
