package org.example.lineprotocol;

import com.google.gson.*;
import org.apache.kafka.common.protocol.types.Field;
import org.example.config.Environment;
import org.example.fhir.MappingYaml;
import org.example.fhir.model.FieldConfig;
import org.example.fhir.model.MeasurementPathConfig;
import org.example.fhir.model.MetadataConfig;
import org.hl7.fhir.r4.model.Meta;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.*;
import java.util.stream.Stream;

import static org.example.JsonUtils.*;

public class LineProtocolParser {

    private static final Logger log = LoggerFactory.getLogger(LineProtocolParser.class);

    public String parse(String category, JsonObject json) throws IllegalArgumentException {
        if (json == null || json.isEmpty() || !json.isJsonObject()) {
            throw new IllegalArgumentException("Input JSON is null, empty or not a JSON object");
        }

        MappingYaml mappingYaml = Environment.TEMPLATE;

        LineProtocolTemplate template = new LineProtocolTemplate();

        MetadataConfig metadataConfig = mappingYaml.getMetadata();
        //find the right config that was used to create the JSON
        MeasurementPathConfig fittingConfig = mappingYaml.getMeasurement().getPaths().stream()
                .filter(e -> e.getPath().equals(category))
                .findFirst()
                .orElse(null);

        if (fittingConfig == null || fittingConfig.getFields() == null || fittingConfig.getFields().isEmpty()) {
            throw new IllegalArgumentException("no rules for mapping fields found even though FHIR was successfully mapped");
        }

        setLPMeasurement(json, fittingConfig, metadataConfig, template);

        setLPTimestamp(json, fittingConfig, metadataConfig, template);

        setLPMaps(json, fittingConfig, metadataConfig, template, "tag");

        setLPMaps(json, fittingConfig, metadataConfig, template, "field");

        return renderLineProtocol(template);
    }

    private static void setLPTimestamp(
            JsonObject json,
            MeasurementPathConfig fittingConfig,
            MetadataConfig metadataConfig,
            LineProtocolTemplate template
    ) {
        List<FieldConfig> timestamp = extractAllFromJson(fittingConfig, metadataConfig,"timestamp");

        if (timestamp.size() != 1) {
            throw new IllegalArgumentException("only one field may be tagged as the LP measurement");
        } else {
            String target = timestamp.get(0).getTarget();
            JsonElement value = getByPath(json, target);

            if (!(value instanceof JsonPrimitive) || !((JsonPrimitive) value).isString()) {
                throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", target, value.toString()));
            }

            String timeNanos = normalizeIsoToNanos(value.getAsString()).toString();

            template.setTimestamp(timeNanos);
        }
    }

    private static void setLPMaps(
            JsonObject json,
            MeasurementPathConfig fittingConfig,
            MetadataConfig metadataConfig,
            LineProtocolTemplate template,
            String type) {
        List<FieldConfig> elements = extractAllFromJson(fittingConfig, metadataConfig, type);

        Map<String, String> elementsMap = new HashMap<>();

        for (FieldConfig f : elements) {

            JsonElement value = getByPath(json, f.getTarget());
            if (!(value instanceof JsonPrimitive)) {
                throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", f.getTarget(), value.toString()));
            }

            String tagValue = value.getAsString();
            String tagKey = f.getLineProtocol().getName();

            elementsMap.put(tagKey, tagValue);
        }

        if (type.equals("field")) {
            template.setFields(elementsMap);
        } else {
            template.setTags(elementsMap);
        }
    }

    private static void setLPMeasurement(
            JsonObject json,
            MeasurementPathConfig fittingConfig,
            MetadataConfig metadataConfig,
            LineProtocolTemplate template
    ) {
        List<FieldConfig> measurement = extractAllFromJson(fittingConfig, metadataConfig, "measurement");

        if (measurement.size() != 1) {
            throw new IllegalArgumentException("only one field may be tagged as the LP measurement");
        } else {
            String target = measurement.get(0).getTarget();
            JsonElement value = getByPath(json, target);

            if (!(value instanceof JsonPrimitive) || !((JsonPrimitive) value).isString()) {
                throw new IllegalArgumentException(String.format("LP transformation failed since value for measurement in FHIR was not primitive string [%s: %s]", target, value.toString()));
            }

            String stringValue = value.getAsJsonPrimitive().getAsString();

            template.setMeasurement(stringValue);
        }
    }

    private static List<FieldConfig> extractAllFromJson(MeasurementPathConfig fittingConfig, MetadataConfig metadataConfig, String type) {
        return Stream.concat(metadataConfig.getFields().stream(), fittingConfig.getFields().stream())
                .filter(f -> f.getLineProtocol() != null)
                .filter(f -> f.getLineProtocol().getType() != null)
                .filter(f -> f.getLineProtocol().getType().equals(type))
                .toList();
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
        }else {
            //with tags with comma
            sb.append(",");
            insertMaps(template.getTags(), sb);
            sb.append(" "); //space between tags and fields
        }

        //set fields
        insertMaps(template.getFields(), sb);

        sb.append(" "); //space between fields and timestamp

        //set timestamp
        sb.append(template.getTimestamp());

        String lpString = sb.toString();
        log.info("Created LP string: {}", lpString);

        return lpString;
    }

    private static void checkAndSetMaps(Map<String, String> map, String type, StringBuilder sb) {

        insertMaps(map, sb);
    }

    private static void insertMaps(Map<String, String> map, StringBuilder sb) {
        Iterator<Map.Entry<String, String>> it = map.entrySet().iterator();

        while (it.hasNext()) {
            Map.Entry<String, String> e = it.next();
            sb.append(e.getKey()).append("=").append(e.getValue());

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
}
