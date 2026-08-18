// Package dashboard builds the data-workbench HTTP responses.
//
// It wraps audited ToolEnvelopes with presentation-layer metadata (DatasetMeta)
// without touching the underlying facts. Per docs/GO_PYTHON_CONTRACT.md, this
// layer performs no financial computation: it maps tool errors to a display
// status, selects a few scalar fields for list rows, and passes the raw
// envelope (data, data_audit, frame_sha256, warnings) through unchanged.
package dashboard

import "encoding/json"

// DataStatus is the display status of a dataset block. It mirrors
// DashboardDataStatus in TASK_research_dashboard.md and never invents a
// severity beyond what ERROR_HANDLING.md defines.
type DataStatus string

const (
	StatusAvailable      DataStatus = "available"
	StatusPartial        DataStatus = "partial"
	StatusStale          DataStatus = "stale"
	StatusUnavailable    DataStatus = "unavailable"
	StatusNotImplemented DataStatus = "not_implemented"
)

// DatasetMeta is the presentation-layer wrapper described in the contract §5.
// Every field is derived from the tool envelope, never from Go-side clocks or
// computation. as_of comes from a tool data field, not time.Now().
type DatasetMeta struct {
	AsOf        string     `json:"as_of"`
	QueriedAt   string     `json:"queried_at"`
	Status      DataStatus `json:"status"`
	SourceTools []string   `json:"source_tools"`
	AuditRefs   []string   `json:"audit_refs"`
	// Warnings passes through ToolEnvelope.data_warnings verbatim.
	Warnings json.RawMessage `json:"warnings,omitempty"`
	// Error passes through ToolEnvelope.error verbatim (original error.code).
	Error json.RawMessage `json:"error,omitempty"`
}

// IndexRow is one row of the index valuation board. The numeric fields are
// copied out of the tool summary for scanning/sorting only; the authoritative
// values (and their audit) remain in the passed-through envelope. A nil pointer
// means the tool did not return that value, which the frontend renders as
// "no data" rather than a zero.
type IndexRow struct {
	Index string      `json:"index"`
	Meta  DatasetMeta `json:"meta"`
	PETTM *Metric     `json:"pe_ttm"`
	PB    *Metric     `json:"pb"`
	// LatestPoint is the latest index level when the tool provides it.
	LatestPoint *float64 `json:"latest_point"`
}

// Metric is a scalar current value plus its historical percentile, copied
// verbatim from summary.pe_ttm / summary.pb.
type Metric struct {
	Current    *float64 `json:"current"`
	Percentile *float64 `json:"percentile"`
	Level      string   `json:"level"`
}

// IndicesResponse is the payload of GET /api/dashboard/indices.
type IndicesResponse struct {
	// Status is the page-level roll-up: available when every index resolved,
	// partial when at least one failed while others succeeded, unavailable when
	// none succeeded.
	Status DataStatus `json:"status"`
	Rows   []IndexRow `json:"rows"`
}
