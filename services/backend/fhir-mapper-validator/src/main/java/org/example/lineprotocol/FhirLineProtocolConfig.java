package org.example.lineprotocol;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.Getter;

import java.util.Collections;
import java.util.List;

@Data
public class FhirLineProtocolConfig {

    @JsonProperty("variants")
    private List<Variant> variants;

    @JsonProperty("measurement-mapping")
    private Mapping measurementMapping;

    @JsonProperty("timestamp-mapping")
    private Mapping timestampMapping;

    @JsonProperty("field-mappings")
    private List<Mapping> fieldMappings;

    @JsonProperty("tag-mappings")
    private List<Mapping> tagMappings; // corrected property name

    public List<Variant> resolvedVariants() {
        if (variants != null && !variants.isEmpty()) return variants;
        boolean legacyDefined = measurementMapping != null
                || timestampMapping != null
                || (fieldMappings != null && !fieldMappings.isEmpty())
                || (tagMappings != null && !tagMappings.isEmpty());
        if (!legacyDefined) return Collections.emptyList();
        Variant fallback = new Variant();
        fallback.setMeasurementMapping(measurementMapping);
        fallback.setTimestampMapping(timestampMapping);
        fallback.setFieldMappings(fieldMappings);
        fallback.setTagMappings(tagMappings);
        return List.of(fallback);
    }

    @Data
    public static class Variant {
        @JsonProperty("measurement-mapping")
        private Mapping measurementMapping;
        @JsonProperty("timestamp-mapping")
        private Mapping timestampMapping;
        @JsonProperty("field-mappings")
        private List<Mapping> fieldMappings;
        @JsonProperty("tag-mappings")
        private List<Mapping> tagMappings;
    }

    @Getter
    public static class Mapping {
        private String source;
        @JsonProperty("allow-array")
        private boolean allowArray;
        private String alias; // optional friendly key name
    }
}
