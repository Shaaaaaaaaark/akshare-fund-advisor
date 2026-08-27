package com.fundadvisor.web.facts;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.List;

public final class ToolEnvelope {

    private final String rawJson;
    private final JsonNode root;

    private ToolEnvelope(String rawJson, JsonNode root) {
        this.rawJson = rawJson;
        this.root = root;
    }

    public static ToolEnvelope parse(String rawJson, ObjectMapper mapper) throws JsonProcessingException {
        JsonNode root = mapper.readTree(rawJson);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException("tool envelope must be a JSON object");
        }
        return new ToolEnvelope(rawJson, root);
    }

    public String rawJson() {
        return rawJson;
    }

    public boolean ok() {
        return root.path("ok").asBoolean(false);
    }

    public JsonNode data() {
        JsonNode data = root.get("data");
        return data == null || data.isNull() ? null : data;
    }

    public String queriedAt() {
        return text(root.get("queried_at"));
    }

    public String errorCode() {
        JsonNode error = root.get("error");
        if (error == null || error.isNull()) {
            return "";
        }
        return text(error.get("code"));
    }

    public String errorRaw(ObjectMapper mapper) {
        return rawField(mapper, "error", true);
    }

    public String warningsRaw(ObjectMapper mapper) {
        return rawField(mapper, "data_warnings", false);
    }

    public List<String> frameHashes() {
        JsonNode audit = root.get("data_audit");
        if (audit == null || !audit.isArray()) {
            return List.of();
        }
        List<String> hashes = new ArrayList<>();
        for (JsonNode item : audit) {
            String hash = text(item.get("frame_sha256"));
            if (!hash.isEmpty()) {
                hashes.add(hash);
            }
        }
        return List.copyOf(hashes);
    }

    private String rawField(ObjectMapper mapper, String field, boolean includeObjects) {
        JsonNode value = root.get(field);
        if (value == null || value.isNull()) {
            return null;
        }
        if (!includeObjects && isEmptyContainer(value)) {
            return null;
        }
        try {
            return mapper.writeValueAsString(value);
        } catch (JsonProcessingException ignored) {
            return null;
        }
    }

    private boolean isEmptyContainer(JsonNode value) {
        return (value.isArray() || value.isObject()) && value.isEmpty();
    }

    public static String text(JsonNode value) {
        if (value == null || value.isNull()) {
            return "";
        }
        return value.asText("");
    }
}
