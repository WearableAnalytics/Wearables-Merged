package org.example.util;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.File;

public class ConfigLoader {

    private static final Logger log = LoggerFactory.getLogger(ConfigLoader.class);

    public static <T> T loadConfig(String path, Class<T> clazz) {
        ObjectMapper mapper = new ObjectMapper(new YAMLFactory());
        mapper.findAndRegisterModules();

        try {
            log.debug("Loading YAML config from path: {}", path);
            return mapper.readValue(new File(path), clazz);
        } catch (Exception e) {
            log.error("Failed to load YAML config from {}", path, e);
            throw new RuntimeException("Failed to load YAML config: " + e.getMessage(), e);
        }
    }
}
