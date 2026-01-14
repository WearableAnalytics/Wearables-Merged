package org.example.fhir;

import com.google.gson.JsonElement;
import org.example.JsonUtils;
import org.example.fhir.model.ValueTransformation;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

import static org.example.JsonUtils.toJsonElement;

public class Transformer {

    private static final Logger log = LoggerFactory.getLogger(Transformer.class);

    static JsonElement resolveAppend(ValueTransformation vt, JsonElement value) {
        String s = JsonUtils.elementToString(value);
        if (s == null)
            throw new RuntimeException(
                    String.format("value for replace [%s] could not be converted to string", value)
            );

        for (String p : vt.getParams()) {
            s = s.concat(p);
        }

        value = toJsonElement(s);
        return value;
    }

    static JsonElement resolveReplace(ValueTransformation vt, JsonElement value) {
        if (vt.getParams() == null || vt.getParams().size() != 2) {
            throw new IllegalArgumentException("replace needs exactly two arguments representing the old and new string");
        }

        String s =  JsonUtils.elementToString(value);
        if (s == null)
            throw new RuntimeException(
                    String.format("value for replace [%s] could not be converted to string", value)
            );

        String target = vt.getParams().get(0);
        String replacement = vt.getParams().get(0);

        Pattern pattern = hasPattern(target);
        if (pattern == null) {
            return toJsonElement(s.replace(target, replacement));
        }

        return toJsonElement(s.replaceAll(pattern.pattern(), replacement));

    }

    private static Pattern hasPattern(String s) {
        try {
            return Pattern.compile(s);
        } catch (PatternSyntaxException pse) {
            return null;
        }
    }

    static JsonElement resolveToLowerCase(ValueTransformation vt, JsonElement value) {
        if (vt.getParams() != null && !vt.getParams().isEmpty())
            log.warn("arguments are not allowed for 'toLowerCase' and will be ignored");

        String s =  JsonUtils.elementToString(value);
        if (s == null)
            throw new IllegalArgumentException(
                    String.format("value `%s' for toLowerCase could not be converted to string", value)
            );

        return toJsonElement(s.toLowerCase());
    }

    static JsonElement substring(ValueTransformation vt, JsonElement value) {
        List<String> params = vt.getParams();

        if (params == null || params.size() != 2) {
            throw new IllegalArgumentException("substring needs exactly two arguments representing beginning and end");
        }

        String s = JsonUtils.elementToString(value);
        if (s == null)
            throw new RuntimeException(
                    String.format("value `%s' for substring could not be converted to string", value)
            );

        int beginning = -1;
        int end = -1;
        try {
            beginning = Integer.parseInt(params.get(0));
            end = Integer.parseInt(params.get(0));
        } catch (NumberFormatException nfe) {
            throw new IllegalArgumentException(String.format("Arguments for substring could not be converted to integers (%s, %s)", params.get(0), params.get(1)));
        }

        return toJsonElement(s.substring(beginning, end));
    }
}
