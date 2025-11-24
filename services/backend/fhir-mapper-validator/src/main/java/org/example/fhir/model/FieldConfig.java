package org.example.fhir.model;

import lombok.Data;

@Data
public class FieldConfig {
    private String name;
    private String source;
    private Object value;
    private String target;
    private boolean optional;
    private String type;
    private boolean mapping;
}
