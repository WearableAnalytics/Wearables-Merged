package org.example;

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

    @Test
    @DisplayName("YAML-driven mapping: measurement, all tags, fields, timestamp")
    public void fullYamlMapping() {
        String lp = parser.parse(SAMPLE_OBS);
        assertNotNull(lp);
        // Measurement
        assertTrue(lp.startsWith("heart-rate,"));
        // Tags (aliases)
        assertTrue(lp.contains(",resource_type=Observation"));
        assertTrue(lp.contains(",category_0=vital-signs"));
        assertTrue(lp.contains(",display_0=Vital_Signs"));
        assertTrue(lp.contains(",category_text=Vital_Signs"));
        assertTrue(lp.contains(",code_0=8867-4"));
        assertTrue(lp.contains(",display_0=Heart_rate"));
        assertTrue(lp.contains(",code_text=Heart_rate"));
        assertTrue(lp.contains(",unit=beats/minute"));
        assertTrue(lp.contains(",unit_code=/min"));
        // Fields
        assertTrue(lp.contains(" value=44i"));
        assertTrue(lp.contains(",status=\"final\""));
        assertTrue(lp.contains(",subject=\"Patient/example\""));
        // Timestamp
        assertTrue(lp.endsWith(" 1762767194000000000"));
    }
}
