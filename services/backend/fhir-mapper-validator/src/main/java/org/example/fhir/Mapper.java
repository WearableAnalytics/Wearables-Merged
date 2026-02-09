package org.example.fhir;

import com.google.gson.*;
import lombok.Data;
import net.sourceforge.plantuml.Run;
import org.example.JsonUtils;
import org.example.config.Environment;
import org.example.dependencies.Node;
import org.example.fhir.model.*;
import org.example.lineprotocol.LineProtocolParser;
import org.javatuples.Pair;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.*;
import java.util.concurrent.SynchronousQueue;

import static org.example.JsonUtils.*;
import static org.example.fhir.FhirTransformer.resolveFhirTransformation;

@Data
public class Mapper {

    private static final Logger log = LoggerFactory.getLogger(Mapper.class);
    private final MappingYaml yaml;
    private final int validationFrq;
    private int validationCounter;

    public Mapper(MappingYaml yaml, int validationFrq) {
        this.yaml = yaml;
        this.validationFrq = validationFrq;
        this.validationCounter = 0;
    }

    public String mapAndValidate(String value, Map<String, Set<Node>> categoryGraphs) {
        try {
            if (value == null || value.isBlank()) {
                log.warn("Pushing empty payload to DLQ");

                //without any incoming data we dont have to continue
                return dlqEmptyPayload();
            }

            Pair<String, JsonObject> categoryFhirTuple = null;
            try {
                categoryFhirTuple = mapFhir(value);
            } catch (IllegalArgumentException e) {
                log.error(e.toString());
                return dlq(e.toString(), value);
            } catch (RuntimeException e) {
                log.warn(e.toString());
                return dlq(e.toString(), value);
            }

            if (categoryFhirTuple.getValue0() == null || categoryFhirTuple.getValue1() == null) {
                log.error("FHIR mapping error occurred: category was not set or FHIR was not produced");
                dlq(
                        "FHIR mapping error occurred: category was not set or FHIR was not produced",
                        value
                );
            }

            JsonObject fhir = categoryFhirTuple.getValue1();
            String category = categoryFhirTuple.getValue0();

            if (fhir == null) {
                log.error("Mapped fhir is null, aborting: {}", value);
                return dlq("Mapped fhir was null, original input attached", value);
            }

            try{
                validationCounter = Validator.validateFhir(fhir, validationCounter);
            }catch(IllegalArgumentException iae){
                log.warn("fhir validation failed with exception: {}", iae.getMessage());
                return dlq("Mapped fhir is not valid", fhir.toString());
            }

            LineProtocolParser lpParser = new LineProtocolParser(yaml);

            try {
                Set<Node> fittingBase = categoryGraphs.get(category);
                return lpParser.parse(category, fhir, fittingBase);

            } catch (IllegalArgumentException iae) {
                log.error("Line Protocol transformation failed", iae);

                // wrap failed LP conversion into DLQ JSON
                return dlq("Line Protocol transformation failed: " + iae.getMessage(), fhir.toString());
            } catch (Exception ex) {
                log.error("Unexpected error during Line Protocol transformation", ex);

                // catch-all DLQ wrapper
                return dlq("Unexpected LP transformation error: " + ex.getMessage(), fhir.toString());
            }


        } catch (
                Exception ex) {
            log.error("Failed to transform payload into FHIR, pushing problematic message to DLQ", ex);
            return dlq(ex.getMessage(), value);
        }
    }

    public Pair<String, JsonObject> mapFhir(String str) throws IllegalArgumentException {
        if (this.yaml == null) {
            throw new IllegalStateException("No mapping template loaded");
        }
        JsonElement parsed = JsonParser.parseString(str);
        if (!parsed.isJsonObject()) {
            throw new RuntimeException("Incoming payload must be a JSON object");
        }
        JsonObject incoming = parsed.getAsJsonObject();
        JsonObject metadataTemplate = buildMetadataBlock(incoming);
        MeasurementConfig measurementCfg = this.yaml.getMeasurement();
        if (measurementCfg == null || measurementCfg.getPaths() == null || measurementCfg.getPaths().isEmpty()) {
            throw new IllegalArgumentException("No measurement paths configured, returning metadata-only document");
        }

        //We return a map that maps from the category / path of the incoming JSON to all FHIR JSONs that were created using that configuration
        for (MeasurementPathConfig pathConfig : measurementCfg.getPaths()) {
            if (pathConfig == null) continue;
            //measurement array is one array of measurements inside the incoming json (e.g., cumulative, period, instantaneous)
            JsonArray measurementArray = resolveMeasurementArray(incoming, pathConfig.getPath());
            if (measurementArray == null) {
                log.warn("Measurement path '{}' not found or not an array", pathConfig.getPath());
                continue;
            }
            if (pathConfig.isArrayMapAll()) {
                if (measurementArray.isEmpty()) continue;
                JsonElement measurementElement = measurementArray.get(0); //There is only one now
                JsonObject outgoingMeasurementTemplate = metadataTemplate.deepCopy().getAsJsonObject();
                boolean res1 = applyFields(outgoingMeasurementTemplate, this.yaml.getMetadata(), null, incoming, measurementElement, 0);
                boolean res2 = applyFields(outgoingMeasurementTemplate, pathConfig, incoming, measurementElement, 0);
                if (!outgoingMeasurementTemplate.isEmpty() && res1 && res2) {
                    return new Pair<>(pathConfig.getPath(), outgoingMeasurementTemplate);
                } else {
                    throw new RuntimeException(String.format("Invalid fhir created through mapping: %s", outgoingMeasurementTemplate));
                }
            } else {
                throw new RuntimeException("Mapping of only a subset of measurements is not yet supported");
                //TODO implement filtering function to decide what to map instead of index based
            }
        }

        throw new RuntimeException(String.format("No measurements were contained in one of the broken down Jsons: %s", str));
    }

    public List<String> flatMapJson(String value) {
        JsonElement rootEl = JsonParser.parseString(value);
        if (!rootEl.isJsonObject()) {
            throw new IllegalArgumentException("Root JSON is not an object");
        }

        JsonObject root = rootEl.getAsJsonObject();

        JsonElement measurementsEl = root.get("measurements");
        if (measurementsEl == null || !measurementsEl.isJsonObject()) {
            throw new IllegalArgumentException("Missing or malformed 'measurements' object");
        }

        JsonObject measurements = measurementsEl.getAsJsonObject();
        List<String> result = new ArrayList<>();

        for (Map.Entry<String, JsonElement> entry : measurements.entrySet()) {
            String listName = entry.getKey();
            JsonElement categoryEl = entry.getValue();

            if (!categoryEl.isJsonArray()) {
                throw new IllegalArgumentException(
                        "Malformed input: measurements." + listName + " is not an array"
                );
            }

            JsonArray categoryArr = categoryEl.getAsJsonArray();

            // For each element in this array, create one output JSON
            for (JsonElement element : categoryArr) {
                // Deep copy the whole root JSON
                JsonObject copy = root.deepCopy();

                JsonObject copiedMeasurements = copy.getAsJsonObject("measurements");

                // Clear ALL measurement arrays in the copy (set each to empty array)
                for (String name : new ArrayList<>(copiedMeasurements.keySet())) {
                    copiedMeasurements.add(name, new JsonArray());
                }

                // Put ONLY this one element into the current list
                JsonArray single = new JsonArray();
                single.add(element.deepCopy()); // deepCopy to be safe
                copiedMeasurements.add(listName, single);

                result.add(copy.toString()); // Gson serializes via toString()
            }
        }

        return result;
    }

    private JsonObject buildMetadataBlock(JsonObject root) {
        JsonObject metadata = new JsonObject();
        MetadataConfig metadataConfig = this.yaml.getMetadata();
        applyFields(metadata, metadataConfig, null, root, null, -1);
        return metadata;
    }

    private JsonArray resolveMeasurementArray(JsonObject root, String path) {
        if (path == null || path.isBlank()) return null;
        JsonElement el = getByPath(root, path);
        if (el == null || !el.isJsonArray()) return null;
        return el.getAsJsonArray();
    }

    //TODO refactor this to be one method with the one below (?)
    private boolean applyFields(JsonObject target,
                                MetadataConfig metadataCfg,
                                MeasurementPathConfig measurementCfg,
                                JsonObject root,
                                JsonElement measurementElement,
                                int idx) {
        if (metadataCfg == null || metadataCfg.getFields() == null || metadataCfg.getFields().isEmpty()) return false;
        for (FieldConfig field : metadataCfg.getFields()) {
            try {
                applySingleFieldRaw(target, field, measurementCfg, root, idx);
            } catch (IllegalStateException ise) {
                log.warn("Found illegal state in metadata, skipping datapoint with exception: {}", ise.toString());
                return false;
            }
        }
        return true;
    }

    private boolean applyFields(
            JsonObject outgoingMeasurementTemplate,
            MeasurementPathConfig pathConfig,
            JsonObject root,
            JsonElement measurementElement, //I have no idea what this does
            int idx
    ) {
        if (pathConfig == null || pathConfig.getFields() == null || pathConfig.getFields().isEmpty()) return false;

        Queue<FieldConfig> fhirDependentQueue = new ArrayDeque<>();
        List<FieldConfig> nonFhirDependent = new ArrayList<>();

        for (FieldConfig field : pathConfig.getFields()) {
            if (field.getFhirSource() != null) {
                log.debug("queue size is {}", fhirDependentQueue.size());
                fhirDependentQueue.add(field);
            } else {
                nonFhirDependent.add(field);
            }
        }

        for (FieldConfig field : nonFhirDependent) {

            try {
                applySingleFieldRaw(outgoingMeasurementTemplate, field, pathConfig, root, idx);
            } catch (IllegalStateException ise) {
                log.warn("Found illegal state in measurements, skipping datapoint with exception: {}", ise.toString());
                return false;
            }
        }

        while (fhirDependentQueue.peek() != null) {

            FieldConfig field = fhirDependentQueue.poll();

            String fhirSource = field.getFhirSource();
            String fhirTarget = field.getTarget();
            JsonElement baseValue = getByPath(outgoingMeasurementTemplate, fhirSource);

            if (baseValue == null) {
                fhirDependentQueue.add(field);
                continue;
            }

            //TODO maybe we can aggregate 'combine' fields in the value since its a json element, would make code cleaner i think with better separation

            JsonElement newValue;
            if (field.getTransform() != null && !field.getTransform().isEmpty()) {
                newValue = resolveFhirTransformation(field, pathConfig, baseValue);
            } else {
                newValue = baseValue;
            }

            setAtTarget(outgoingMeasurementTemplate, fhirTarget, newValue);

        }

        return true;
    }

    private void applySingleFieldRaw(
            JsonObject outgoingElementTemplate,
            FieldConfig field,
            MeasurementPathConfig measurementCfg,
            JsonObject rootOfIncoming,
            int idx) throws IllegalArgumentException {
        if (field == null) return;
        if (field.getTarget() == null || field.getTarget().isBlank()) {
            log.warn("Skipping field '{}' because outgoingElementTemplate is missing", field.getName());
            return;
        }
        JsonElement value;
        //1. We retreive either a value or a source field

        if (field.getValue() != null) {
            //log.debug("found field that needs to be retrieved from value: {}", field.getName());
            value = toJsonElement(field.getValue());
        } else {
            //log.debug("found field {} that needs to be retrieved from source: {}", field.getName(), field.getSource());
            String sourcePath = expandPathForMeasurement(field.getRawSource(), measurementCfg, idx);
            if (sourcePath == null || sourcePath.isBlank()) {
                if (!field.isOptional()) {
                    throw new IllegalArgumentException("Field '" + field.getName() + "' lacks a source/value but is required");
                }
                return;
            }

            JsonElement baseValue = getByPath(rootOfIncoming, sourcePath);

            if (baseValue == null || baseValue.isJsonNull()) {
                throw new IllegalArgumentException(String.format("Value for path '%s' is empty or null", sourcePath));
            }

            if (field.getTransform() != null && !field.getTransform().isEmpty()) {
                value = RawTransformer.resolveRawTransformation(field, measurementCfg, baseValue);
            } else {
                value = baseValue;
            }
        }

        if (value == null || value.isJsonNull()) {
            if (!field.isOptional()) {
                throw new IllegalArgumentException(String.format("Missing value for required field '%s' with target '%s'", field.getName(), field.getTarget()));
            }
            return;
        }
        JsonUtils.setAtTarget(outgoingElementTemplate, field.getTarget(), deepCopyElement(value));
    }

    private static String dlq(String error, String payload) {
        return """
                {
                    "valid": false,
                    "error": "%s",
                    "payload": %s
                }
                """.formatted(
                escape(error),
                payload == null ? "null" : "\"" + escape(payload) + "\""
        ).trim();
    }

    private static String dlqEmptyPayload() {
        return """
                {
                    "valid": false,
                    "error": "Empty payload",
                    "payload": null
                }
                """.trim();
    }

    private static String escape(String s) {
        return s == null ? null : s.replace("\"", "\\\"");
    }

}
