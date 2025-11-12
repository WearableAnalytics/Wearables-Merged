package org.example.lineprotocol;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.util.List;

@Data
public class FhirLineProtocolConfig {

    @JsonProperty("measurement-mapping")
    private Mapping measurementMapping;

    @JsonProperty("timestamp-mapping")
    private Mapping timestampMapping;

    @JsonProperty("field-mappings")
    private List<Mapping> fieldMappings;

    @JsonProperty("tag-mappings")
    private List<Mapping> tagMappings; // corrected property name

    public static class Mapping {
        private String source;
        @JsonProperty("allow-array")
        private boolean allowArray;
        private String alias; // optional friendly key name
        public String getSource() { return source; }
        public boolean isAllowArray() { return allowArray; }
        public String getAlias() { return alias; }
    }
}
