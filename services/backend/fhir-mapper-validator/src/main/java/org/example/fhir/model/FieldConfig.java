package org.example.fhir.model;

import lombok.Data;

import java.util.List;

@Data
public class FieldConfig {
    private String name;
    private String rawSource; //TODO change everywhere
    private String fhirSource;
    private Object value;
    private String target;
    private List<ValueTransformation> transform;
    private boolean optional;
    private String type;
    private LineProtocol lineProtocol;
}

//fhirType;
//end;
//unit;
//value;
//type;
//status;
//start;
//device;
