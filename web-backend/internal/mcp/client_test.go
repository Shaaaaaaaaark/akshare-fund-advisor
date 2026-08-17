package mcp

import (
	"encoding/json"
	"testing"
)

// TestUnwrapEnvelopeNested confirms the optional {"result": <envelope>} nesting
// is unwrapped.
func TestUnwrapEnvelopeNested(t *testing.T) {
	structured := json.RawMessage(`{"result":{"tool":"index_valuation","ok":true}}`)
	out := unwrapEnvelope(structured)
	var env Envelope
	if err := json.Unmarshal(out, &env); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if env.Tool != "index_valuation" || !env.OK {
		t.Fatalf("unwrap nested failed: %+v", env)
	}
}

// TestUnwrapEnvelopeFlat confirms a real multi-key ToolEnvelope is not
// misread as a nested wrapper.
func TestUnwrapEnvelopeFlat(t *testing.T) {
	structured := json.RawMessage(`{"tool":"index_valuation","ok":true,"result":{"nested":1}}`)
	out := unwrapEnvelope(structured)
	var env Envelope
	if err := json.Unmarshal(out, &env); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if env.Tool != "index_valuation" {
		t.Fatalf("flat envelope was wrongly unwrapped: %s", out)
	}
}

// TestEnvelopePassThrough confirms data / data_audit stay as raw bytes and are
// not re-typed or re-rounded.
func TestEnvelopePassThrough(t *testing.T) {
	raw := json.RawMessage(`{
		"tool":"index_valuation","ok":true,
		"data":{"summary":{"pe_ttm":{"current":13.6200001}}},
		"data_audit":[{"frame_sha256":"abc"}],
		"queried_at":"2026-08-14T00:00:00+08:00"
	}`)
	var env Envelope
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	// The exact float text must survive because Data is json.RawMessage.
	if got := string(env.Data); got != `{"summary":{"pe_ttm":{"current":13.6200001}}}` {
		t.Errorf("data mutated during decode: %s", got)
	}
	if got := string(env.DataAudit); got != `[{"frame_sha256":"abc"}]` {
		t.Errorf("data_audit mutated during decode: %s", got)
	}
}
