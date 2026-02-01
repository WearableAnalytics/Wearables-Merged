package org.example.lineprotocol;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonPrimitive;
import lombok.Data;
import lombok.Getter;
import org.example.dependencies.Node;

import java.time.Instant;
import java.util.*;

import static org.example.JsonUtils.getByPath;

@Data
public class LineProtocolTemplate {

    public LineProtocolTemplate(JsonObject json, Set<Node> minimalBase){
        this.fields = new HashMap<>();
        this.tags = new HashMap<>();

        this.json = json;
        this.minimalBase = minimalBase;
    }

    private JsonObject json;
    private Set<Node> minimalBase;

    @JsonProperty("measurement-mapping")
    private String measurement;
    @JsonProperty("timestamp-mapping")
    private String timestamp;
    @JsonProperty("field-mappings")
    private Map<String, String> fields;
    @JsonProperty("tag-mappings")
    private Map<String, String> tags;


    @Getter
    public static class Mapping {
        private String source;
        @JsonProperty("allow-array")
        private boolean allowArray;
        private String alias; // optional friendly key name
    }

    public LineProtocolTemplate setTimestamp() {

        Node timestampNode = this.minimalBase.stream()
                .filter(x -> x.getField().getLineProtocol().getType().equals("timestamp"))
                .findFirst()
                .orElse(null);

        if (timestampNode == null) {
            throw new RuntimeException("there was no node marked as a timestamp node, this should not happen here");
        }

        String target = timestampNode.getField().getTarget();
        JsonElement value = getByPath(this.json, target);

        if (!(value instanceof JsonPrimitive) || !((JsonPrimitive) value).isString()) {
            throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", target, value.toString()));
        }

        String timeNanos = normalizeIsoToNanos(value.getAsString()).toString();

        this.setTimestamp(timeNanos);

    }

    public LineProtocolTemplate setMaps(String type) {

        Map<String, String> elementsMap = new HashMap<>();

        this.minimalBase.stream()
                .map(Node::getField)
                .filter(field -> field.getLineProtocol().getType().equals(type))
                .forEach(
                        x -> {
                            JsonElement value = getByPath(this.json, x.getTarget());
                            if (!(value instanceof JsonPrimitive)) {
                                throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", x.getTarget(), value.toString()));
                            }

                            String tagValue = value.getAsString();
                            String tagKey = x.getLineProtocol().getName();

                            elementsMap.put(tagKey, tagValue);
                        }
                );

        if (type.equals("field")) {
            this.setFields(elementsMap);
        } else {
            this.setTags(elementsMap);
        }

        return this;
    }

    public LineProtocolTemplate setMeasurement() {

        Node measurementNode = this.minimalBase.stream()
                .filter(x -> x.getField().getLineProtocol().getType().equals("measurement"))
                .findFirst()
                .orElse(null);

        if (measurementNode == null) {
            throw new RuntimeException("there was no node marked as measurement node, this should not happen here");
        }

        String target = measurementNode.getField().getTarget();
        JsonElement value = getByPath(this.json, target);

        if (!(value instanceof JsonPrimitive) || !((JsonPrimitive) value).isString()) {
            throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", target, value.toString()));
        }

        String stringValue = value.getAsJsonPrimitive().getAsString();

        this.setMeasurement(stringValue);

        return this;
    }

    private static Long normalizeIsoToNanos(String str) {
        try {
            // Parse ISO 8601 string (handles Z or offset like +02:00)
            Instant instant = Instant.parse(str);
            // Convert to nanos since epoch
            return instant.getEpochSecond() * 1_000_000_000L + instant.getNano();
        } catch (Exception e) {
            throw new IllegalArgumentException("Invalid ISO 8601 datetime: " + str, e);
        }
    }

}
