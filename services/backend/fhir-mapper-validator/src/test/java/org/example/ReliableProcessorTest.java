package org.example;

import com.google.gson.*;
import org.example.dependencies.DependencyGraph;
import org.example.dependencies.Node;
import org.example.fhir.Mapper;
import org.example.fhir.Validator;
import org.example.fhir.model.MappingYaml;
import org.junit.BeforeClass;
import org.junit.Test;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Instant;
import java.util.*;

import static org.junit.Assert.*;

public class ReliableProcessorTest {
    private static Mapper mapper;
    private static Map<String, Set<Node>> graphs;
    private static final byte[] KEY = "ssssssssssssssssssssssssssssssss".getBytes(StandardCharsets.UTF_8);
    private static final String PATIENT = "11111111-1111-4111-8111-111111111111";

    @BeforeClass
    public static void initialize() {
        Validator.initiliazeFhirValidator(0);
        MappingYaml mapping = ConfigLoader.loadConfig("config/mapping-2026-01-28.yaml", MappingYaml.class);
        mapper = new Mapper(mapping, 100);
        DependencyGraph graph = new DependencyGraph(mapping);
        graph.createGraphBase();
        graph.enrichGraphWithFhir();
        graphs = graph.build();
    }

    private JsonObject data(String type, String time) {
        return JsonParser.parseString("""
                {"deviceInfo":{"platform":"iOS","deviceId":"phone-installation-9"},
                 "participantId":"%s","sourceName":"synthetic-test","sourcePlatform":"test-provider",
                 "measurements":{"instantaneous":[{"type":"%s","value":72.12345678901234,
                 "unit":"BEATS_PER_MINUTE","timestamp":"%s"}],"cumulative":[],"duration":[]}}
                """.formatted(PATIENT, type, time)).getAsJsonObject();
    }

    private String input(JsonObject data) throws Exception {
        JsonObject body = new JsonObject();
        body.addProperty("recordId", "22222222-2222-4222-8222-222222222222");
        body.addProperty("generation", 1);
        body.addProperty("inputSha256", "b".repeat(64));
        body.add("data", data);
        String payload = Base64.getEncoder().encodeToString(body.toString().getBytes(StandardCharsets.UTF_8));
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(KEY, "HmacSHA256"));
        String signature = HexFormat.of().formatHex(mac.doFinal((ReliableProcessor.INPUT_KIND + "." + payload).getBytes(StandardCharsets.UTF_8)));
        JsonObject envelope = new JsonObject();
        envelope.addProperty("kind", ReliableProcessor.INPUT_KIND);
        envelope.addProperty("payload", payload);
        envelope.addProperty("signature", signature);
        return envelope.toString();
    }

    private JsonObject result(String wire) {
        JsonObject envelope = JsonParser.parseString(wire).getAsJsonObject();
        return JsonParser.parseString(new String(Base64.getDecoder().decode(envelope.get("payload").getAsString()),
                StandardCharsets.UTF_8)).getAsJsonObject();
    }

    @Test
    public void invalidFhirActuallyThrowsInsteadOfBeingSwallowed() {
        assertThrows(IllegalArgumentException.class, () -> Validator.validateAlways(
                JsonParser.parseString("{\"resourceType\":\"Observation\"}").getAsJsonObject()));
    }

    @Test
    public void validFhirDoesNotAlwaysThrow() {
        Validator.validateAlways(JsonParser.parseString("""
                {"resourceType":"Observation","status":"final","code":{"text":"Synthetic test"}}
                """).getAsJsonObject());
    }

    @Test
    public void fhirSubjectAndSenderAreSeparate() {
        JsonObject fhir = mapper.mapFhir(data("HEART_RATE", "2026-10-30T10:15:00").toString()).getValue1();
        assertEquals("Patient/" + PATIENT, fhir.getAsJsonObject("subject").get("reference").getAsString());
        assertEquals("phone-installation-9", fhir.getAsJsonObject("device").get("display").getAsString());
    }

    @Test
    public void signedReadingKeepsValueAndOffsetInstant() throws Exception {
        ReliableProcessor processor = new ReliableProcessor(mapper, graphs, KEY, "a".repeat(64));
        JsonObject result = result(processor.process(input(data("HEART_RATE", "2026-10-30T12:15:00+02:00"))));
        assertEquals(result.toString(), "normalized", result.get("status").getAsString());
        String line = result.get("lineProtocol").getAsString();
        assertTrue(line, line.contains("value=72.12345678901234"));
        assertTrue(line, line.endsWith(" " + Instant.parse("2026-10-30T10:15:00Z").getEpochSecond() * 1_000_000_000L));
        assertTrue(line, line.contains("source-device-id=phone-installation-9"));
        assertTrue(line, line.contains("device-id-reference=Patient/" + PATIENT));
    }

    @Test
    public void tamperedInputCannotProduceAnAuthenticatedOutcome() throws Exception {
        ReliableProcessor processor = new ReliableProcessor(mapper, graphs, KEY, "a".repeat(64));
        String wire = input(data("HEART_RATE", "2026-10-30T10:15:00Z"));
        JsonObject changed = JsonParser.parseString(wire).getAsJsonObject();
        changed.addProperty("signature", "0".repeat(64));
        assertNull(processor.process(changed.toString()));
    }

    @Test
    public void unmappedRecordReturnsARejectionWithoutHealthDataInTheError() throws Exception {
        ReliableProcessor processor = new ReliableProcessor(mapper, graphs, KEY, "a".repeat(64));
        JsonObject outcome = result(processor.process(input(data("UNMAPPED_TEST_METRIC", "2026-10-30T10:15:00Z"))));
        assertEquals("rejected", outcome.get("status").getAsString());
        assertFalse(outcome.has("lineProtocol"));
        assertFalse(outcome.has("payload"));
        assertTrue(outcome.has("mapperVersion"));
    }

    @Test
    public void versionIncludesTheMappingBytes() throws Exception {
        String current = ReliableProcessor.artifactVersion(Path.of("config/mapping-2026-01-28.yaml"));
        Path other = java.nio.file.Files.createTempFile("mapping-version", ".yaml");
        try {
            java.nio.file.Files.writeString(other, "different configuration");
            assertNotEquals(current, ReliableProcessor.artifactVersion(other));
        } finally {
            java.nio.file.Files.delete(other);
        }
    }

    @Test
    public void senderIdentifierIsEscapedWithoutChangingParticipantIdentity() throws Exception {
        JsonObject data = data("HEART_RATE", "2026-10-30T10:15:00Z");
        data.getAsJsonObject("deviceInfo").addProperty("deviceId", "phone one,part=2");
        ReliableProcessor processor = new ReliableProcessor(mapper, graphs, KEY, "a".repeat(64));
        String line = result(processor.process(input(data))).get("lineProtocol").getAsString();
        assertTrue(line, line.contains("source-device-id=phone\\ one\\,part\\=2"));
        assertTrue(line, line.contains("device-id-reference=Patient/" + PATIENT));
    }

    @Test
    public void transportSettingsCannotOverrideProcessingOrHostnameVerification() {
        var properties = new java.util.Properties();
        org.example.config.KafkaConfig.applyTransportSecurity(properties, "{\"security.protocol\":\"SSL\"}");
        assertEquals("SSL", properties.getProperty("security.protocol"));
        assertThrows(IllegalArgumentException.class, () -> org.example.config.KafkaConfig.applyTransportSecurity(
                properties, "{\"ssl.endpoint.identification.algorithm\":\"\"}"));
        assertThrows(IllegalArgumentException.class, () -> org.example.config.KafkaConfig.applyTransportSecurity(
                properties, "{\"processing.guarantee\":\"at_least_once\"}"));
    }
}
