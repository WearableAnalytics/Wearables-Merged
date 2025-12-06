package org.example.fhir;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import org.example.fhir.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.Objects;

import static org.example.fhir.Mapper.*;

public class Transformations {

    private static final Logger log = LoggerFactory.getLogger(Transformations.class);

    static JsonElement resolveMappingValue(FieldConfig field,
                                           MeasurementPathConfig measurementCfg,
                                           JsonObject root,
                                           JsonElement measurementElement) {
        if (measurementCfg == null || measurementCfg.getMappings() == null) {
            log.warn("Field '{}' flagged as mapping but no mappings configured", field.getName());
            return null;
        }
        MappingRuleConfig ruleConfig = measurementCfg.getMappings().stream()
                .filter(rule -> rule != null && Objects.equals(rule.getPath(), field.getTarget()))
                .findFirst()
                .orElse(null);
        if (ruleConfig == null) {
            log.warn("No mapping rule found for target '{}'", field.getTarget());
            return null;
        }
        String basedOnPath = ruleConfig.getBasedOn();
        JsonElement basedOnValue = getByPath(root, basedOnPath);
        if ((basedOnValue == null || basedOnValue.isJsonNull()) && measurementElement != null) {
            String relative = deriveRelativePath(ruleConfig.getBasedOn(), measurementCfg.getPath());
            if (relative != null) {
                basedOnValue = relative.isEmpty() ? measurementElement : getByPath(measurementElement, relative);
            }
        }
        if (basedOnValue == null || basedOnValue.isJsonNull()) {
            log.warn("Mapping rule for '{}' missing basedOn value at path '{}'", field.getTarget(), ruleConfig.getBasedOn());
            return null;
        }
        String key = primitiveAsString(basedOnValue);
        if (key == null) {
            log.warn("Mapping rule for '{}' could not convert basedOn value to string", field.getTarget());
            return null;
        }
        List<RuleConfig> rules = ruleConfig.getMap();
        if (rules == null) {
            log.warn("Mapping rule for '{}' has no map entries", field.getTarget());
            return null;
        }
        for (RuleConfig rule : rules) {
            if (rule != null && Objects.equals(rule.getKey(), key)) {
                return toJsonElement(rule.getValue());
            }
        }
        log.warn("Mapping rule for '{}' does not contain key '{}'", field.getTarget(), key);
        return null;
    }

    static String elementToString(JsonElement je){
        String valueAsString = null;
        try {
            valueAsString = je.getAsString();
        } catch (IllegalStateException ise){
            throw new RuntimeException("toLowerCase can only be called on fields that can be cast to string, but was a JsonObject, JsonArray or null");
        }
        return valueAsString;
    }
}
