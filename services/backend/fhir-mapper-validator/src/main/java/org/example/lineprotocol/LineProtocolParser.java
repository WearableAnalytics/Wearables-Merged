package org.example.lineprotocol;

import com.google.gson.*;
import org.example.config.Environment;
import org.example.dependencies.Node;
import org.example.fhir.model.MappingYaml;
import org.example.fhir.model.FieldConfig;
import org.example.fhir.model.MeasurementPathConfig;
import org.example.fhir.model.MetadataConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.*;
import java.util.stream.Stream;

import static org.example.JsonUtils.*;

public class LineProtocolParser {

    private static final Logger log = LoggerFactory.getLogger(LineProtocolParser.class);

    public String parse(String category, JsonObject json, Set<Node> minimalBase) throws IllegalArgumentException {
        if (json == null || json.isEmpty() || !json.isJsonObject()) {
            throw new IllegalArgumentException("Input JSON is null, empty or not a JSON object");
        }

        LineProtocolTemplate template = new LineProtocolTemplate();

        setLPMeasurement(json, template, minimalBase);

        setLPTimestamp(json, template, minimalBase);

        setLPMaps(json, template, "tag", minimalBase);

        setLPMaps(json, template, "field", minimalBase);

        return renderLineProtocol(template);
    }

    private static void setLPTimestamp(
            JsonObject json,
            LineProtocolTemplate template,
            Set<Node> minimalBase
    ) {

        Node timestampNode = minimalBase.stream()
                .filter(x -> x.getField().getLineProtocol().getType().equals("timestamp"))
                .findFirst()
                .orElse(null);

        if (timestampNode == null) {
            throw new RuntimeException("there was no node marked as a timestamp node, this should not happen here");
        }

        String target = timestampNode.getField().getTarget();
        JsonElement value = getByPath(json, target);

        if (!(value instanceof JsonPrimitive) || !((JsonPrimitive) value).isString()) {
            throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", target, value.toString()));
        }

        String timeNanos = normalizeIsoToNanos(value.getAsString()).toString();

        template.setTimestamp(timeNanos);

    }

    private static void setLPMaps(
            JsonObject json,
            LineProtocolTemplate template,
            String type,
            Set<Node> minimalBase
    ) {

        Map<String, String> elementsMap = new HashMap<>();

        minimalBase.stream()
                .map(Node::getField)
                .filter(field -> field.getLineProtocol().getType().equals(type))
                .forEach(
                        x -> {
                            JsonElement value = getByPath(json, x.getTarget());
                            if (!(value instanceof JsonPrimitive)) {
                                throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", x.getTarget(), value.toString()));
                            }

                            String tagValue = value.getAsString();
                            String tagKey = x.getLineProtocol().getName();

                            elementsMap.put(tagKey, tagValue);
                        }
                );

        if (type.equals("field")) {
            template.setFields(elementsMap);
        } else {
            template.setTags(elementsMap);
        }
    }

    private static void setLPMeasurement(
            JsonObject json,
            LineProtocolTemplate template,
            Set<Node> baseNodes
    ) {

        Node measurementNode = baseNodes.stream()
                .filter(x -> x.getField().getLineProtocol().getType().equals("measurement"))
                .findFirst()
                .orElse(null);

        if (measurementNode == null) {
            throw new RuntimeException("there was no node marked as measurement node, this should not happen here");
        }

        String target = measurementNode.getField().getTarget();
        JsonElement value = getByPath(json, target);

        if (!(value instanceof JsonPrimitive) || !((JsonPrimitive) value).isString()) {
            throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", target, value.toString()));
        }

        String stringValue = value.getAsJsonPrimitive().getAsString();

        template.setMeasurement(stringValue);

    }

    private String renderLineProtocol(LineProtocolTemplate template) {
        if (template.getMeasurement() == null) {
            throw new IllegalArgumentException("Template missing measurement-mapping");
        }
        if (template.getTimestamp() == null) {
            throw new IllegalArgumentException("Template missing timestamp");
        }
        if (template.getFields() == null || template.getFields().isEmpty()) {
            throw new IllegalArgumentException("Template has no fields");
        }

        StringBuilder sb = new StringBuilder();

        //set measurement
        sb.append(template.getMeasurement());

        if (template.getTags() == null || template.getTags().isEmpty()) {
            //no tags with space
            sb.append(" ");
        } else {
            //with tags with comma
            sb.append(",");
            insertMaps("tag", template.getTags(), sb);
            sb.append(" "); //space between tags and fields
        }

        //set fields
        insertMaps("field", template.getFields(), sb);

        sb.append(" "); //space between fields and timestamp

        //set timestamp
        sb.append(template.getTimestamp());

        String lpString = sb.toString();
        log.info("Created LP string: {}", lpString);

        return lpString;
    }

    private static void insertMaps(String type, Map<String, String> map, StringBuilder sb) {
        Iterator<Map.Entry<String, String>> it = map.entrySet().iterator();

        while (it.hasNext()) {
            Map.Entry<String, String> e = it.next();

            boolean b = checkNumber(e.getValue());

            String quotedIfString = e.getValue();

            //if it's a field AND not a number, it needs to be quoted, in all other cases it doesn't
            if (type.equals("field") && !b) {
                quotedIfString = "\"" + e.getValue() + "\"";
            }

            sb.append(e.getKey()).append("=").append(quotedIfString);

            if (it.hasNext()) {
                sb.append(",");
            }
        }
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

    private static boolean checkNumber(String s) {

        try {
            Float.parseFloat(s);
            return true;
        } catch (NumberFormatException ignored) {
            return false;
        }

    }
}
