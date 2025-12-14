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

    public List<Variant> resolvedVariants() {
        if (variants != null && !variants.isEmpty()) return variants;
        return Collections.emptyList();
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
