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

import javax.sound.sampled.Line;
import java.time.Instant;
import java.util.*;
import java.util.stream.Stream;

import static org.example.JsonUtils.*;

public class LineProtocolParser {

    private static final Logger log = LoggerFactory.getLogger(LineProtocolParser.class);

    public LineProtocolParser(MappingYaml yaml){
        this.yaml = yaml;
    }

    MappingYaml yaml;

    public String parse(String category, JsonObject json, Set<Node> minimalBase) throws IllegalArgumentException {
        if (json == null || json.isEmpty() || !json.isJsonObject()) {
            throw new IllegalArgumentException("Input JSON is null, empty or not a JSON object");
        }

        LineProtocolTemplate template = new LineProtocolTemplate(json, minimalBase, this.yaml);

        LineProtocolTemplate filled = template
                .setMeasurement()
                .setTimestamp()
                .setMaps("tag")
                .setMaps("field")
                .setCategory(category)
                .setVersion();

        return renderLineProtocol(filled);
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

    private static boolean checkNumber(String s) {

        try {
            Float.parseFloat(s);
            return true;
        } catch (NumberFormatException ignored) {
            return false;
        }

    }


}
