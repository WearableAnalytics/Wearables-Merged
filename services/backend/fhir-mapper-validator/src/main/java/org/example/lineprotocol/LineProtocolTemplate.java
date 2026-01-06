package org.example.lineprotocol;

import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;
import lombok.Getter;

import java.util.*;

@Data
public class LineProtocolTemplate {

    public LineProtocolTemplate(){
        fields = new HashMap<>();
        tags = new HashMap<>();
    }

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
}
