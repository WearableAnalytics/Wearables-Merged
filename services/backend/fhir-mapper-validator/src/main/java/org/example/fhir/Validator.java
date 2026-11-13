package org.example.fhir;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.context.support.DefaultProfileValidationSupport;
import ca.uhn.fhir.parser.IParser;
import ca.uhn.fhir.validation.FhirValidator;
import ca.uhn.fhir.validation.IValidatorModule;
import ca.uhn.fhir.validation.ValidationResult;
import com.google.gson.JsonObject;
import org.hl7.fhir.common.hapi.validation.support.CommonCodeSystemsTerminologyService;
import org.hl7.fhir.common.hapi.validation.support.InMemoryTerminologyServerValidationSupport;
import org.hl7.fhir.common.hapi.validation.support.SnapshotGeneratingValidationSupport;
import org.hl7.fhir.common.hapi.validation.support.ValidationSupportChain;
import org.hl7.fhir.common.hapi.validation.validator.FhirInstanceValidator;
import org.hl7.fhir.instance.model.api.IBaseResource;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Validator {

    private static final Logger log = LoggerFactory.getLogger(Validator.class);

    private static FhirValidator validator;
    // Use a cached context and reuse it for parsing and validation
    private static FhirContext CTX;
    private static int validationFrq;

    public static void initiliazeFhirValidator(int validationFrequency) {

        log.info("Initializing FHIR validator (with caching)...");
        long start = System.currentTimeMillis();

        CTX = FhirContext.forR4Cached();
        validator = CTX.newValidator();
        validationFrq = validationFrequency;

        ValidationSupportChain.CacheConfiguration.defaultValues();

        ValidationSupportChain validationSupportChain = new ValidationSupportChain(
                new DefaultProfileValidationSupport(CTX),
                new CommonCodeSystemsTerminologyService(CTX),
                new InMemoryTerminologyServerValidationSupport(CTX),
                new SnapshotGeneratingValidationSupport(CTX)
        );

        IValidatorModule module = new FhirInstanceValidator(validationSupportChain);
        validator.registerValidatorModule(module);

        long end = System.currentTimeMillis();
        log.info("FHIR validator initialized in {} ms", (end - start));
    }

    public static int validateFhir(JsonObject produced, Integer counter) {
        if (validationFrq != 0 && counter < validationFrq) return counter + 1;
        validateAlways(produced);
        return 0;
    }

    public static void validateAlways(JsonObject produced) {
        if (validator == null) throw new IllegalStateException("FHIR validator is not initialized");
        final IBaseResource resource;
        try {
            resource = CTX.newJsonParser().parseResource(produced.toString());
        } catch (Exception ex) {
            throw new IllegalArgumentException("FHIR resource could not be parsed");
        }
        ValidationResult result = validator.validateWithResult(resource);
        if (!result.isSuccessful()) throw new IllegalArgumentException("FHIR resource failed validation");
    }
}
