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

    public static int validateFhir(JsonObject producedStr, Integer counter){

        if (validationFrq != 0 && counter < validationFrq) {
            counter++;
            return counter;
        }

        try {
            // Parse once to avoid internal re-parsing costs and validate the resource instance
            IParser parser = CTX.newJsonParser();
            IBaseResource resource = parser.parseResource(producedStr.toString());
            ValidationResult result = validator.validateWithResult(resource);
            log.debug("Validation result: {}", result.toString());
            throw new IllegalArgumentException(String.format("Fhir validation failed with result: %s", result));
        } catch (Exception e) {
            log.error("Validation failed (input may not be a valid FHIR resource).", e);
            return 0;
        }
    }

}
