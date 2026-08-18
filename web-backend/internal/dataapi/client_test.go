package dataapi

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestCallToolMapsDashboardOperationToREST(t *testing.T) {
	var requestPath string
	var requestQuery string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requestPath = r.URL.Path
		requestQuery = r.URL.RawQuery
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{
			"schema_version":"1.0",
			"request_id":"7d9b9c4f-b2b4-4a25-8137-4a24c4634f68",
			"tool":"index_valuation",
			"ok":true,
			"data":{"summary":{"pe_ttm":{"current":13.6200001}}},
			"sources":[],
			"data_audit":[{"frame_sha256":"audit-hash"}],
			"data_warnings":[],
			"data_policy":{"ai_may_generate_market_data":false},
			"queried_at":"2026-08-18T00:00:00+08:00",
			"error":null
		}`))
	}))
	defer server.Close()

	client := New(server.URL, time.Second)
	raw, envelope, err := client.CallTool(
		context.Background(),
		"index_valuation",
		map[string]any{
			"index":      "沪深300",
			"years":      10,
			"max_points": 600,
		},
	)
	if err != nil {
		t.Fatalf("CallTool: %v", err)
	}

	if requestPath != "/v1/indices/沪深300" {
		t.Fatalf("path = %q", requestPath)
	}
	if requestQuery != "max_points=600&years=10" {
		t.Fatalf("query = %q", requestQuery)
	}
	if !envelope.OK || envelope.Tool != "index_valuation" {
		t.Fatalf("unexpected envelope: %+v", envelope)
	}
	if got := string(envelope.Data); got != `{"summary":{"pe_ttm":{"current":13.6200001}}}` {
		t.Fatalf("data precision changed: %s", got)
	}
	var roundTrip map[string]any
	if err := json.Unmarshal(raw, &roundTrip); err != nil {
		t.Fatalf("raw envelope invalid: %v", err)
	}
	if roundTrip["request_id"] != "7d9b9c4f-b2b4-4a25-8137-4a24c4634f68" {
		t.Fatalf("raw envelope changed: %s", raw)
	}
}

func TestRouteRejectsUnknownDashboardOperation(t *testing.T) {
	_, _, err := route("fund_analyze", nil)
	if err == nil {
		t.Fatal("expected unsupported operation error")
	}
}
