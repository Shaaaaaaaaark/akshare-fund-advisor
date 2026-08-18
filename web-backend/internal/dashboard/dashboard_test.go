package dashboard

import (
	"encoding/json"
	"testing"

	"github.com/akshare-fund-advisor/web-backend/internal/facts"
)

func TestMapStatus(t *testing.T) {
	cases := []struct {
		name string
		env  *facts.Envelope
		want DataStatus
	}{
		{"ok", &facts.Envelope{OK: true}, StatusAvailable},
		{"nil", nil, StatusUnavailable},
		{
			"not_found",
			&facts.Envelope{OK: false, Error: &facts.ToolError{Code: "INDEX_NOT_SUPPORTED"}},
			StatusUnavailable,
		},
		{
			"upstream",
			&facts.Envelope{OK: false, Error: &facts.ToolError{Code: "DATA_SOURCE_ERROR"}},
			StatusUnavailable,
		},
		{
			"stale",
			&facts.Envelope{OK: false, Error: &facts.ToolError{Code: "STALE_OR_INVALID_DATA"}},
			StatusStale,
		},
		{"error_missing", &facts.Envelope{OK: false}, StatusUnavailable},
	}
	for _, tc := range cases {
		if got := mapStatus(tc.env); got != tc.want {
			t.Errorf("%s: mapStatus = %q, want %q", tc.name, got, tc.want)
		}
	}
}

func TestRollUp(t *testing.T) {
	cases := []struct {
		name string
		in   []DataStatus
		want DataStatus
	}{
		{"empty", nil, StatusUnavailable},
		{"all_ok", []DataStatus{StatusAvailable, StatusAvailable}, StatusAvailable},
		{"none_ok", []DataStatus{StatusUnavailable, StatusUnavailable}, StatusUnavailable},
		{"mixed", []DataStatus{StatusAvailable, StatusUnavailable}, StatusPartial},
		{"stale_only", []DataStatus{StatusStale}, StatusStale},
		{"stale_and_ok", []DataStatus{StatusAvailable, StatusStale}, StatusStale},
		{"fail_beats_stale", []DataStatus{StatusStale, StatusUnavailable}, StatusPartial},
	}
	for _, tc := range cases {
		if got := rollUp(tc.in); got != tc.want {
			t.Errorf("%s: rollUp = %q, want %q", tc.name, got, tc.want)
		}
	}
}

// TestFrameHashesPassThrough confirms Go reads frame_sha256 verbatim from
// data_audit without altering it.
func TestFrameHashesPassThrough(t *testing.T) {
	audit := json.RawMessage(`[
		{"interface":"stock_index_pe_lg","frame_sha256":"abc123"},
		{"interface":"stock_index_pb_lg","frame_sha256":"def456"},
		{"interface":"noop"}
	]`)
	got := frameHashes(audit)
	want := []string{"abc123", "def456"}
	if len(got) != len(want) {
		t.Fatalf("frameHashes len = %d, want %d (%v)", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("frameHashes[%d] = %q, want %q", i, got[i], want[i])
		}
	}
}

// TestFillFromDataNoSynthesis confirms scalar selection copies tool values and
// leaves missing values nil rather than zero-filling them.
func TestFillFromDataNoSynthesis(t *testing.T) {
	data := json.RawMessage(`{
		"summary":{
			"pe_ttm":{"current":13.62,"percentile":90.11,"level":"high"},
			"pb":{"current":1.43,"percentile":75.27,"level":"upper_middle"}
		},
		"charts":{
			"pe_ttm":{"latest_date":"2026-08-14"},
			"index_points":{"current":4012.5}
		}
	}`)
	var row IndexRow
	fillFromData(&row, nil, data)

	if row.PETTM == nil || row.PETTM.Current == nil || *row.PETTM.Current != 13.62 {
		t.Fatalf("pe_ttm.current not copied verbatim: %+v", row.PETTM)
	}
	if row.PB == nil || row.PB.Percentile == nil || *row.PB.Percentile != 75.27 {
		t.Fatalf("pb.percentile not copied verbatim: %+v", row.PB)
	}
	if row.Meta.AsOf != "2026-08-14" {
		t.Errorf("as_of = %q, want tool latest_date 2026-08-14", row.Meta.AsOf)
	}
	if row.LatestPoint == nil || *row.LatestPoint != 4012.5 {
		t.Errorf("latest_point not copied verbatim: %+v", row.LatestPoint)
	}
}

// TestFillFromDataMissingMetric confirms a missing metric stays nil.
func TestFillFromDataMissingMetric(t *testing.T) {
	data := json.RawMessage(`{"summary":{"pe_ttm":{"current":10.0,"percentile":50.0,"level":"middle"}},"charts":{"pe_ttm":{"latest_date":"2026-08-14"}}}`)
	var row IndexRow
	fillFromData(&row, nil, data)
	if row.PB != nil {
		t.Errorf("pb should stay nil when tool omits it, got %+v", row.PB)
	}
	if row.LatestPoint != nil {
		t.Errorf("latest_point should stay nil when index_points absent, got %+v", *row.LatestPoint)
	}
}

func TestFillFromDataUsesPBDateWhenPEIsMissing(t *testing.T) {
	data := json.RawMessage(`{
		"summary":{"pe_ttm":null,"pb":{"current":1.43,"percentile":75.27,"level":"upper_middle"}},
		"charts":{"pe_ttm":null,"pb":{"latest_date":"2026-08-15"}}
	}`)
	var row IndexRow
	fillFromData(&row, nil, data)

	if row.PETTM != nil {
		t.Fatalf("pe_ttm should remain nil, got %+v", row.PETTM)
	}
	if row.PB == nil || row.PB.Current == nil || *row.PB.Current != 1.43 {
		t.Fatalf("pb not copied verbatim: %+v", row.PB)
	}
	if row.Meta.AsOf != "2026-08-15" {
		t.Fatalf("as_of = %q, want PB latest_date", row.Meta.AsOf)
	}
}

func TestETFEnvelopeMetaPassesAuditWarningAndError(t *testing.T) {
	env := &facts.Envelope{
		OK:           false,
		QueriedAt:    "2026-08-18T01:00:00+08:00",
		DataAudit:    json.RawMessage(`[{"frame_sha256":"etf-hash"}]`),
		DataWarnings: json.RawMessage(`[{"code":"SOURCE_UNAVAILABLE"}]`),
		Error: &facts.ToolError{
			Code:      "UPSTREAM_TIMEOUT",
			Message:   "timeout",
			Retryable: true,
		},
	}

	meta := envelopeMeta(env, etfDashboardTool, "2026-08-17")

	if meta.AsOf != "2026-08-17" || meta.Status != StatusUnavailable {
		t.Fatalf("unexpected meta: %+v", meta)
	}
	if len(meta.AuditRefs) != 1 || meta.AuditRefs[0] != "etf-hash" {
		t.Fatalf("audit refs not preserved: %+v", meta.AuditRefs)
	}
	if string(meta.Warnings) != `[{"code":"SOURCE_UNAVAILABLE"}]` {
		t.Fatalf("warnings changed: %s", meta.Warnings)
	}
	if !json.Valid(meta.Error) {
		t.Fatalf("error is not valid JSON: %s", meta.Error)
	}
}
