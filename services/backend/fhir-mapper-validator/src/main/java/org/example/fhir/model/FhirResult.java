package org.example.fhir.model;

public record FhirResult(boolean valid, String payload, String error){}

