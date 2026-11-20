package org.example;

import com.google.gson.*;
import org.example.dependencies.Node;
import org.example.fhir.Mapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;
import java.util.stream.Stream;

/** Signed, receipt-backed records return a result to the delivery journal.
 * The journal reserves the final database point before publishing line protocol.
 * Historical raw records continue through the original topology.
 */
public final class ReliableProcessor {
    public static final String INPUT_KIND = "wearables.ingestion/1";
    public static final String RESULT_KIND = "wearables.ingestion-result/1";
    private final Mapper mapper;
    private final Map<String, Set<Node>> graphs;
    private final byte[] key;
    private final String version;

    public ReliableProcessor(Mapper mapper, Map<String, Set<Node>> graphs, byte[] key, String version) {
        if (key.length != 32 || !version.matches("[a-f0-9]{64}")) throw new IllegalArgumentException("Invalid processing configuration");
        this.mapper = mapper;
        this.graphs = graphs;
        this.key = key.clone();
        this.version = version;
    }

    public static boolean isEnvelope(String value) {
        try {
            JsonElement kind = JsonParser.parseString(value).getAsJsonObject().get("kind");
            return kind != null && kind.isJsonPrimitive() && kind.getAsString().startsWith("wearables.ingestion/");
        } catch (RuntimeException ex) {
            return false;
        }
    }

    public static String artifactVersion(Path mapping) throws Exception {
        MessageDigest hash = MessageDigest.getInstance("SHA-256");
        hash.update("reliable-ingestion/1".getBytes(StandardCharsets.UTF_8));
        hash.update(Files.readAllBytes(mapping));
        Path artifact = Path.of(ReliableProcessor.class.getProtectionDomain().getCodeSource().getLocation().toURI());
        if (Files.isDirectory(artifact)) {
            try (Stream<Path> entries = Files.walk(artifact)) {
                for (Path path : entries.filter(Files::isRegularFile).sorted().toList()) {
                    hash.update(artifact.relativize(path).toString().getBytes(StandardCharsets.UTF_8));
                    hash.update(Files.readAllBytes(path));
                }
            }
        } else {
            try (var input = Files.newInputStream(artifact)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = input.read(buffer)) >= 0) hash.update(buffer, 0, read);
            }
        }
        return HexFormat.of().formatHex(hash.digest());
    }

    private byte[] mac(String value) throws Exception {
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(key, "HmacSHA256"));
        return mac.doFinal(value.getBytes(StandardCharsets.UTF_8));
    }

    public String signResult(JsonObject result) throws Exception {
        String payload = Base64.getEncoder().encodeToString(result.toString().getBytes(StandardCharsets.UTF_8));
        JsonObject envelope = new JsonObject();
        envelope.addProperty("kind", RESULT_KIND);
        envelope.addProperty("payload", payload);
        envelope.addProperty("signature", HexFormat.of().formatHex(mac(RESULT_KIND + "." + payload)));
        return envelope.toString();
    }

    private JsonObject verifiedInput(String wire) throws Exception {
        if (wire.length() > 1_100_000) throw new IllegalArgumentException("Oversized input");
        JsonObject envelope = JsonParser.parseString(wire).getAsJsonObject();
        String payload = envelope.get("payload").getAsString();
        if (!INPUT_KIND.equals(envelope.get("kind").getAsString()) || !MessageDigest.isEqual(
                mac(INPUT_KIND + "." + payload), HexFormat.of().parseHex(envelope.get("signature").getAsString()))) {
            throw new IllegalArgumentException("Untrusted input");
        }
        JsonObject body = JsonParser.parseString(new String(Base64.getDecoder().decode(payload), StandardCharsets.UTF_8)).getAsJsonObject();
        UUID.fromString(body.get("recordId").getAsString());
        if (!body.get("inputSha256").getAsString().matches("[a-f0-9]{64}") || body.get("generation").getAsInt() < 1) {
            throw new IllegalArgumentException("Invalid input identity");
        }
        return body;
    }

    private static void normalizeTimes(JsonElement value) {
        if (value.isJsonArray()) {
            for (JsonElement element : value.getAsJsonArray()) normalizeTimes(element);
        } else if (value.isJsonObject()) {
            JsonObject object = value.getAsJsonObject();
            Set<String> times = Set.of("timestamp", "periodStart", "periodEnd", "startTime", "endTime");
            for (String name : new ArrayList<>(object.keySet())) {
                JsonElement field = object.get(name);
                if (times.contains(name) && field.isJsonPrimitive() && field.getAsJsonPrimitive().isString()) {
                    String text = field.getAsString();
                    final LocalDateTime utc;
                    if (text.endsWith("Z") || text.matches(".*[+-]\\d\\d:\\d\\d$")) {
                        utc = OffsetDateTime.parse(text).withOffsetSameInstant(ZoneOffset.UTC).toLocalDateTime();
                    } else {
                        // Historical clients sent local-looking times. Preserve the
                        // old UTC assumption; their receipt says upload-only identity.
                        utc = LocalDateTime.parse(text);
                    }
                    object.addProperty(name, utc.format(java.time.format.DateTimeFormatter.ISO_LOCAL_DATE_TIME));
                } else normalizeTimes(field);
            }
        }
    }

    public String process(String wire) {
        final JsonObject input;
        try {
            input = verifiedInput(wire);
        } catch (Exception ex) {
            return null; // Retained raw input is retried by the journal; no forged result.
        }
        JsonObject result = new JsonObject();
        result.add("recordId", input.get("recordId"));
        result.add("generation", input.get("generation"));
        result.add("inputSha256", input.get("inputSha256"));
        result.addProperty("mapperVersion", version);
        String error = null;
        try {
            JsonObject data = input.getAsJsonObject("data").deepCopy();
            normalizeTimes(data);
            List<String> records = mapper.flatMapJson(data.toString());
            if (records.size() != 1) throw new IllegalArgumentException("Expected one source record");
            String mapped = mapper.mapAndValidate(records.get(0), graphs, true);
            if (mapped.startsWith("{")) {
                String reason = JsonParser.parseString(mapped).getAsJsonObject().get("error").getAsString();
                error = reason.equals("Mapped fhir is not valid") ? "fhir_validation_failed" : "mapping_failed";
            } else result.addProperty("lineProtocol", mapped);
        } catch (DateTimeException ex) {
            error = "timestamp_failed";
        } catch (RuntimeException ex) {
            error = "mapping_failed";
        }
        result.addProperty("status", error == null ? "normalized" : "rejected");
        if (error != null) result.addProperty("errorCode", error);
        try {
            return signResult(result);
        } catch (Exception ex) {
            throw new IllegalStateException("Cannot authenticate processing result");
        }
    }
}
