package org.example.fhir;

import lombok.Data;

// Mapping represents one mapping from a type in the Input to a type in the output
@Data
public class Mapping {
    private String source;
    private String target; // optional in yaml; defaults to source when null
    private String type;
    private boolean optional;
}
