package org.example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;
import java.io.FileReader;
import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Properties;
import java.util.concurrent.CountDownLatch;

import ca.uhn.fhir.context.FhirContext;
import ca.uhn.fhir.context.support.DefaultProfileValidationSupport;
import ca.uhn.fhir.sl.cache.CacheFactory;
import ca.uhn.fhir.validation.FhirValidator;
import ca.uhn.fhir.validation.IValidatorModule;
import ca.uhn.fhir.validation.SchemaBaseValidator;
import ca.uhn.fhir.validation.ValidationResult;
import com.fasterxml.jackson.core.exc.StreamReadException;
import com.fasterxml.jackson.databind.DatabindException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.google.gson.*;
import lombok.Data;
import netscape.javascript.JSObject;
import org.apache.kafka.common.serialization.Serdes;
import org.apache.kafka.streams.KafkaStreams;
import org.apache.kafka.streams.StreamsBuilder;
import org.apache.kafka.streams.StreamsConfig;
import org.apache.kafka.streams.Topology;
import org.apache.kafka.streams.kstream.KStream;
import org.apache.kafka.streams.kstream.ValueMapper;
// ADD these instead:
import ca.uhn.fhir.context.support.IValidationSupport;
import ca.uhn.fhir.context.support.ValidationSupportContext;
import org.hl7.fhir.common.hapi.validation.support.CommonCodeSystemsTerminologyService;
import org.hl7.fhir.common.hapi.validation.support.InMemoryTerminologyServerValidationSupport;
import org.hl7.fhir.common.hapi.validation.support.SnapshotGeneratingValidationSupport;
import org.hl7.fhir.common.hapi.validation.support.ValidationSupportChain;
import org.hl7.fhir.common.hapi.validation.validator.FhirInstanceValidator;
import org.hl7.fhir.r4.model.*;
import org.hl7.fhir.r4.model.Bundle;
import com.fasterxml.jackson.databind.JsonNode;
import com.github.victools.jsonschema.generator.OptionPreset;
import com.github.victools.jsonschema.generator.SchemaGenerator;
import com.github.victools.jsonschema.generator.SchemaGeneratorConfig;
import com.github.victools.jsonschema.generator.SchemaGeneratorConfigBuilder;
import com.github.victools.jsonschema.generator.SchemaVersion;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

public class Main {

    private static final Logger log = LoggerFactory.getLogger(Main.class);

    // Rule describing how to map a source path to a target path and whether it's optional.
    static class MappingRule {
        final String target;
        final boolean optional;
        final ValueTransformer transformer; // extensible hook for future transformations

        MappingRule(String target, boolean optional, ValueTransformer transformer) {
            this.target = target;
            this.optional = optional;
            this.transformer = transformer == null ? ValueTransformer.identity() : transformer;
        }
    }

    // Simple transformation functional interface to keep the pipeline extensible
    interface ValueTransformer {
        JsonElement apply(JsonElement in);

        static ValueTransformer identity() {
            return v -> v;
        }
    }

    // Token model for navigating/creating JSON structures
    static abstract class PathToken {
    }

    static final class FieldToken extends PathToken {
        final String name;

        FieldToken(String n) {
            this.name = n;
        }
    }

    static final class IndexToken extends PathToken {
        final int index;

        IndexToken(int i) {
            this.index = i;
        }
    }


    final static String INPUT_TOPIC = "wearables-raw";
    final static String OUTPUT_TOPIC = "wearables-fhri";
    final static String KAFKA_BROKER_ENV_VAR = "KAFKA_BROKER";
    final static String APP_ID = "fhri-mapper";
    private static FhirValidator validator;
    // Use a cached context and reuse it for parsing and validation
    private static FhirContext CTX;

    // We need to be able to choose between multiple yaml files for multiple providers
    final static MappingYaml yaml = readYaml("src/main/resources/test.yaml");

    //TODO we need to cahnge this so one input can produce multiple outputs
    public static void main(String[] args) throws InterruptedException {

        initiliazeFhirValidator();

        StreamsBuilder builder = new StreamsBuilder();
        KStream<String, String> lowerCaseStrings = builder.stream(INPUT_TOPIC);
        KStream<String, String> upperCaseStrings = lowerCaseStrings.mapValues(new ValueMapper<String, String>() {
            @Override
            public String apply(String str) {
                try {
                    log.debug("Using slf4j for logging");
                    log.debug("Received message payload: {}", str);

                    if (yaml == null || yaml.getMappingsList() == null) {
                        log.error("There was an error reading the mapping yaml");
                        return "";
                    }

                    log.debug("Using yaml to transform: {}", yaml.getMappingsList().toString());
                    JsonElement root = JsonParser.parseString(str);

                    // Build mapping map from YAML: source -> (target, optional)
                    java.util.Map<String, MappingRule> rules = buildSourceRuleMap(yaml);

                    // Traverse input and build output according to rules
                    JsonObject output = new JsonObject();
                    java.util.Set<String> foundSources = new java.util.HashSet<>();
                    traverseAndApply(root, "", output, rules, foundSources);

                    // Verify that all non-optional mappings are present in input
                    java.util.List<String> missingRequired = new java.util.ArrayList<>();
                    for (java.util.Map.Entry<String, MappingRule> e : rules.entrySet()) {
                        if (!e.getValue().optional && !foundSources.contains(e.getKey())) {
                            missingRequired.add(e.getKey());
                        }
                    }
                    if (!missingRequired.isEmpty()) {
                        String msg = "Missing required fields in input for sources: " + missingRequired;
                        log.error("{} | foundSources={} rules={}", msg, foundSources, rules.keySet());
                        throw new RuntimeException(msg);
                    }

                    String outStr = output.toString();
                    log.debug("Produced mapped payload: {}", outStr);

                    if (validate(outStr)) {
                        return outStr;
                    } else {
                        return "";
                    }
                } catch (Exception ex) {
                    log.error("Transformation failed with exception", ex);
                    return "";
                }
            }
        });
        upperCaseStrings.to(OUTPUT_TOPIC);

        Topology topology = builder.build();
        KafkaStreams streamsApp = new KafkaStreams(topology, getKafkaStreamsConfig());
        streamsApp.start();
        log.info("Kafka Streams application '{}' started. Topology description:\n{}", APP_ID, topology.describe());

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            log.info("Shutdown signal received. Closing Kafka Streams application '{}'...", APP_ID);
            streamsApp.close();
            log.info("Kafka Streams application '{}' closed.", APP_ID);
        }));
        new CountDownLatch(1).await();
    }

    private static void initiliazeFhirValidator() {

        log.info("Initializing FHIR validator (with caching)...");
        long start = System.currentTimeMillis();

        // Use cached context to avoid repeated classpath scans
        CTX = FhirContext.forR4Cached();
        validator = CTX.newValidator();

        ValidationSupportChain.CacheConfiguration.defaultValues();

        // Build a local validation support chain and wrap it in a cache
        ValidationSupportChain validationSupportChain = new ValidationSupportChain(
                new DefaultProfileValidationSupport(CTX),
                new CommonCodeSystemsTerminologyService(CTX),
                new InMemoryTerminologyServerValidationSupport(CTX),
                new SnapshotGeneratingValidationSupport(CTX)
        );

        fetchFhirStuff(validationSupportChain);

        IValidatorModule module = new FhirInstanceValidator(validationSupportChain);
        validator.registerValidatorModule(module);

        long end = System.currentTimeMillis();
        log.info("FHIR validator initialized in {} ms", (end - start));

        // Pre-warm the caches with a minimal resource validation
        try {
            long warmStart = System.currentTimeMillis();
            Patient p = new Patient();
            p.addName().setFamily("warmup").addGiven("warm");
            p.setId("warm-1");
            ValidationResult warm = validator.validateWithResult(p);
            long warmEnd = System.currentTimeMillis();
            log.info("FHIR validator warm-up took {} ms, ok={}", (warmEnd - warmStart), warm.isSuccessful());
        } catch (Exception e) {
            log.warn("Warm-up validation failed: {}", e.getMessage());
        }
    }

    // Build a map from source path -> MappingRule (target, optional)
    static java.util.Map<String, MappingRule> buildSourceRuleMap(MappingYaml yamlCfg) {
        java.util.Map<String, MappingRule> map = new java.util.HashMap<>();
        if (yamlCfg == null || yamlCfg.getMappingsList() == null) return map;
        for (Mapping m : yamlCfg.getMappingsList()) {
            if (m == null) continue;
            String source = m.getSource() == null ? null : m.getSource().trim();
            if (source == null || source.isEmpty()) continue;
            String target = (m.getTarget() != null && !m.getTarget().trim().isEmpty()) ? m.getTarget().trim() : source;
            boolean optional = m.isOptional(); // defaults to false if missing
            MappingRule rule = new MappingRule(target, optional, ValueTransformer.identity());
            map.put(source, rule);
        }
        return map;
    }

    // Traverse input JSON and apply mapping rules where the current path matches a rule
    static void traverseAndApply(JsonElement element,
                                 String path,
                                 JsonObject out,
                                 java.util.Map<String, MappingRule> rules,
                                 java.util.Set<String> foundSources) {
        if (element == null || element.isJsonNull()) {
            if (!path.isEmpty() && rules.containsKey(path)) {
                MappingRule r = rules.get(path);
                log.debug("Applying mapping for null at path='{}' -> target='{}' (optional={})", path, r.target, r.optional);
                JsonElement transformed = r.transformer.apply(JsonNull.INSTANCE);
                setAtTarget(out, r.target, transformed);
                foundSources.add(path);
            }
            return;
        }
        if (element.isJsonPrimitive()) {
            if (!path.isEmpty() && rules.containsKey(path)) {
                MappingRule r = rules.get(path);
                log.debug("Applying mapping at primitive path='{}' -> target='{}' (optional={}) value={}", path, r.target, r.optional, element);
                JsonElement transformed = r.transformer.apply(element);
                setAtTarget(out, r.target, transformed);
                foundSources.add(path);
            }
            return;
        }
        if (element.isJsonArray()) {
            JsonArray arr = element.getAsJsonArray();
            for (int i = 0; i < arr.size(); i++) {
                String next = path.isEmpty() ? ("[" + i + "]") : (path + "[" + i + "]");
                traverseAndApply(arr.get(i), next, out, rules, foundSources);
            }
            return;
        }
        if (element.isJsonObject()) {
            JsonObject obj = element.getAsJsonObject();
            for (java.util.Map.Entry<String, JsonElement> e : obj.entrySet()) {
                String key = e.getKey();
                JsonElement child = e.getValue();
                String next = path.isEmpty() ? key : path + "." + key;
                traverseAndApply(child, next, out, rules, foundSources);
            }
        }
    }

    // Set a value inside the output JsonObject according to a dot/[index] path, creating structures as needed
    static void setAtTarget(JsonObject root, String targetPath, JsonElement value) {
        java.util.List<PathToken> tokens = tokenize(targetPath);
        if (tokens.isEmpty()) return;
        JsonElement current = root;
        for (int i = 0; i < tokens.size(); i++) {
            PathToken t = tokens.get(i);
            boolean last = (i == tokens.size() - 1);
            if (t instanceof FieldToken f) {
                JsonObject obj = current.getAsJsonObject();
                if (last) {
                    log.debug("setAtTarget: setting field '{}' with value={} (last token)", f.name, value);
                    obj.add(f.name, deepCopyElement(value));
                } else {
                    PathToken nextTok = tokens.get(i + 1);
                    JsonElement next = obj.get(f.name);
                    if (next == null || next.isJsonNull()) {
                        next = (nextTok instanceof IndexToken) ? new JsonArray() : new JsonObject();
                        obj.add(f.name, next);
                        log.debug("setAtTarget: created {} for field '{}'", (nextTok instanceof IndexToken) ? "JsonArray" : "JsonObject", f.name);
                    }
                    current = next;
                }
            } else if (t instanceof IndexToken idx) {
                // current should be a JsonArray here
                JsonArray arr;
                if (current.isJsonArray()) {
                    arr = current.getAsJsonArray();
                } else {
                    // Create array if current isn't array (edge case: target path starting with index)
                    arr = new JsonArray();
                    log.debug("setAtTarget: created JsonArray for index token at position {}", i);
                    // We need a parent to attach this array; to keep code simple, we assume index isn't first token
                    // If it is, we attach under a default key "_root".
                    // But normally, previous step ensures array container exists.
                }
                while (arr.size() <= idx.index) arr.add(JsonNull.INSTANCE);
                if (last) {
                    log.debug("setAtTarget: setting array index {} with value={} (last token)", idx.index, value);
                    arr.set(idx.index, deepCopyElement(value));
                    current = arr.get(idx.index);
                } else {
                    PathToken nextTok = tokens.get(i + 1);
                    JsonElement next = arr.get(idx.index);
                    if (next == null || next.isJsonNull()) {
                        next = (nextTok instanceof IndexToken) ? new JsonArray() : new JsonObject();
                        arr.set(idx.index, next);
                        log.debug("setAtTarget: created {} at array index {}", (nextTok instanceof IndexToken) ? "JsonArray" : "JsonObject", idx.index);
                    }
                    current = next;
                }
            }
        }
    }

    static java.util.List<PathToken> tokenize(String path) {
        java.util.ArrayList<PathToken> tokens = new java.util.ArrayList<>();
        if (path == null || path.isBlank()) return tokens;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < path.length(); i++) {
            char c = path.charAt(i);
            if (c == '.') {
                if (sb.length() > 0) {
                    tokens.add(new FieldToken(sb.toString()));
                    sb.setLength(0);
                }
            } else if (c == '[') {
                if (sb.length() > 0) {
                    tokens.add(new FieldToken(sb.toString()));
                    sb.setLength(0);
                }
                int j = i + 1;
                int num = 0;
                while (j < path.length() && Character.isDigit(path.charAt(j))) {
                    num = num * 10 + (path.charAt(j) - '0');
                    j++;
                }
                // expect closing ']'
                if (j < path.length() && path.charAt(j) == ']') {
                    tokens.add(new IndexToken(num));
                    i = j; // advance
                } else {
                    // malformed, treat as literal
                    tokens.add(new FieldToken("["));
                }
            } else {
                sb.append(c);
            }
        }
        if (sb.length() > 0) {
            tokens.add(new FieldToken(sb.toString()));
        }
        return tokens;
    }

    static JsonElement deepCopyElement(JsonElement in) {
        if (in == null) return JsonNull.INSTANCE;
        try {
            return JsonParser.parseString(in.toString());
        } catch (Exception e) {
            return in; // fallback
        }
    }

    static Properties getKafkaStreamsConfig() {

        // Read broker info from environment variable KAFKA_BROKER
        String envValue = System.getenv(KAFKA_BROKER_ENV_VAR);

        String bootstrapServers;
        if (envValue == null || envValue.trim().isEmpty()) {
            // Fallback to sensible default
            bootstrapServers = "localhost:9092";
            log.warn("Env var '{}' not set. Using default bootstrap servers: {}", KAFKA_BROKER_ENV_VAR, bootstrapServers);
        } else {
            String trimmed = envValue.trim();
            // If the value already looks like a full bootstrap servers string (contains ':' or commas), use as-is
            if (trimmed.contains(":") || trimmed.contains(",")) {
                bootstrapServers = trimmed;
            } else {
                // Treat it as a host and append the default Kafka port
                bootstrapServers = trimmed + ":9092";
            }
            log.info("Using bootstrap servers from env '{}': {}", KAFKA_BROKER_ENV_VAR, bootstrapServers);
        }

        Properties configurations = new Properties();

        configurations.put(StreamsConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        configurations.put(StreamsConfig.APPLICATION_ID_CONFIG, APP_ID);
        configurations.put(StreamsConfig.DEFAULT_KEY_SERDE_CLASS_CONFIG, org.apache.kafka.common.serialization.Serdes.String().getClass().getName());
        configurations.put(StreamsConfig.DEFAULT_VALUE_SERDE_CLASS_CONFIG, org.apache.kafka.common.serialization.Serdes.String().getClass().getName());

        configurations.put(StreamsConfig.REQUEST_TIMEOUT_MS_CONFIG, "20000");
        configurations.put(StreamsConfig.RETRY_BACKOFF_MS_CONFIG, "500");

        return configurations;
    }

    static boolean validate(String producedStr){

        try {
            // Parse once to avoid internal re-parsing costs and validate the resource instance
            var parser = CTX.newJsonParser();
            var resource = parser.parseResource(producedStr);
            ValidationResult result = validator.validateWithResult(resource);
            log.info("Validation result: {}", result.toString());
            return result.isSuccessful();
        } catch (Exception e) {
            log.error("Validation failed (input may not be a valid FHIR resource).", e);
            return false;
        }
    }

    //for debugging
    static void fetchFhirStuff(ValidationSupportChain dpvs) {
        if (dpvs == null) {
            log.error("DefaultProfileValidationSupport (dpvs) is null.");
            return;
        }

        Object conformanceResources = dpvs.fetchAllConformanceResources();
        if (conformanceResources != null) {
            log.info("Conformance resources: {}", conformanceResources.toString());
        } else {
            log.warn("Conformance resources are null.");
        }

        Object nonBaseStructureDefs = dpvs.fetchAllNonBaseStructureDefinitions();
        if (nonBaseStructureDefs != null) {
            log.info("Non base structure definitions: {}", nonBaseStructureDefs.toString());
        } else {
            log.warn("Non base structure definitions are null.");
        }

//        Object searchParameters = dpvs.fetchAllSearchParameters();
//        if (searchParameters != null) {
//            SLog.i("Search parameters: %s", searchParameters.toString());
//        } else {
//            SLog.w("Search parameters are null.");
//        }

        Object name = dpvs.getName();
        if (name != null) {
            log.info("Name: {}", name.toString());
        } else {
            log.warn("Name is null.");
        }
    }

    // We read the provided YAML from the user and check if it's fits the requirements of the "meta-yaml".
    // We only have to do this once in the beginning since I propose we restart the tasks / pods after we added a new provider
    static MappingYaml readYaml(String path) {

        // TODO validate the user yaml somehow
        ObjectMapper mapper = new ObjectMapper(new YAMLFactory());

        mapper.findAndRegisterModules();

        String externalPath = System.getenv("MAPPING_YAML_PATH");
        try {
            log.info("Loading YAML from external path: {}", externalPath);

            String content = Files.readString(Paths.get(externalPath));
            System.out.println("YAML content:\n" + content);

            MappingYaml t = mapper.readValue(new File(externalPath), MappingYaml.class);

            if (t == null){
                log.debug("t is null");
            } else if (t.getMappingsList() == null){
                log.debug("list is null, t is {}", t);
            }
            return t;
        } catch (IOException e) {
            log.error(String.format("Failed to load mapping YAML (externalPath=%s, providedPath=%s)", externalPath, path), e);
            throw new RuntimeException("Failed to load mapping YAML: " + e.getMessage(), e);
        }
    }

}

@Data
class MappingYaml {
    private List<Mapping> mappingsList;
}

// Mapping represents one mapping from a type in the Input to a type in the output
@Data
class Mapping {
    private String source;
    private String target; // optional in yaml; defaults to source when null
    private String type;
    private boolean optional;
}
