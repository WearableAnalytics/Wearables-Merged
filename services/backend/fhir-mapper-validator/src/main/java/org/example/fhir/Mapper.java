package org.example.fhir;

import com.google.gson.*;
import lombok.Data;
import org.example.JsonUtils;
import org.example.fhir.model.*;
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

    public Mapper(MappingYaml yaml) {
        this.yaml = yaml;
    }

    public Map<String, MapReturn> mapFhir(String str) {
        if (this.yaml == null) {
            throw new IllegalStateException("No mapping template loaded");
        }
        JsonElement parsed = JsonParser.parseString(str);
        if (!parsed.isJsonObject()) {
            throw new IllegalArgumentException("Incoming payload must be a JSON object");
        }
        JsonObject incoming = parsed.getAsJsonObject();
        JsonObject metadataTemplate = buildMetadataBlock(incoming);
        MeasurementConfig measurementCfg = this.yaml.getMeasurement();
        if (measurementCfg == null || measurementCfg.getPaths() == null || measurementCfg.getPaths().isEmpty()) {
            log.warn("No measurement paths configured – returning metadata-only document");
            return new HashMap<>();
        }

        //We return a map that maps from the category / path of the incoming JSON to all FHIR JSONs that were created using that configuration
        Map<String, MapReturn> observations = new HashMap<>();
        for (MeasurementPathConfig pathConfig : measurementCfg.getPaths()) {
            List<JsonObject> valid = new ArrayList<>();
            List<JsonObject> invalid = new ArrayList<>();
            if (pathConfig == null) continue;
            //measurement array is one array of measurements inside the incoming json (e.g., cumulative, period, instantaneous)
            JsonArray measurementArray = resolveMeasurementArray(incoming, pathConfig.getPath());
            if (measurementArray == null) {
                log.warn("Measurement path '{}' not found or not an array", pathConfig.getPath());
                continue;
            }
            if (pathConfig.isArrayMapAll()) {
                for (int idx = 0; idx < measurementArray.size(); idx++) {
                    JsonElement measurementElement = measurementArray.get(idx);
                    JsonObject outgoingMeasurementTemplate = metadataTemplate.deepCopy().getAsJsonObject();
                    boolean res1 = applyFields(outgoingMeasurementTemplate, this.yaml.getMetadata(), null, incoming, measurementElement, idx);
                    boolean res2 = applyFields(outgoingMeasurementTemplate, pathConfig, incoming, measurementElement, idx);
                    if (!outgoingMeasurementTemplate.isEmpty() && res1 && res2) valid.add(outgoingMeasurementTemplate);
                    else invalid.add(outgoingMeasurementTemplate);
                }
            } else {
                throw new RuntimeException("Mapping of only a subset of measurements is not yet supported");
                //TODO implement filtering function to decide what to map instead of index based
            }
            MapReturn mr = new MapReturn(valid, invalid);
            observations.put(pathConfig.getPath(), mr);
        }
        return observations;
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
                log.info("queue size is {}", fhirDependentQueue.size());
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

}
