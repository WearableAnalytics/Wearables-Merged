package org.example.fhir.model;

import com.google.gson.JsonObject;
import lombok.Data;

import java.util.List;

@Data
public class MapReturn {
    List<JsonObject> valid;
    List<JsonObject> invalid;

    public MapReturn(List<JsonObject> validIn, List<JsonObject> invalidIn){
        valid = validIn;
        invalid = invalidIn;
    }
}
