package org.example.fhir.model;

import lombok.Data;

import java.util.List;

@Data
public class ValueTransformation {
    private String type;
    private List<String> params;
}
