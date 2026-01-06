package org.example.fhir.model;

import lombok.Data;

import java.util.List;

@Data
public class FieldConfig {
    private String name;
    private String source;
    private Object value;
    private String target;
    private List<ValueTransformation> transform;
    private boolean optional;
    private String type;
    private LineProtocol lineProtocol;
}
