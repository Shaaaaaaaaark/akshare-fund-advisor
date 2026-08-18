// Package facts defines the audited market-data envelope shared by internal
// transports. It contains no MCP or HTTP behavior.
package facts

import "encoding/json"

// Envelope mirrors the Python ToolEnvelope produced by the audited data core.
// Market data and audit evidence stay as raw JSON so Go never rewrites them.
type Envelope struct {
	SchemaVersion string          `json:"schema_version"`
	RequestID     string          `json:"request_id"`
	Tool          string          `json:"tool"`
	OK            bool            `json:"ok"`
	Data          json.RawMessage `json:"data"`
	Sources       json.RawMessage `json:"sources"`
	DataAudit     json.RawMessage `json:"data_audit"`
	DataWarnings  json.RawMessage `json:"data_warnings"`
	DataPolicy    json.RawMessage `json:"data_policy"`
	QueriedAt     string          `json:"queried_at"`
	Error         *ToolError      `json:"error"`
}

// ToolError is the typed portion of an audited envelope error.
type ToolError struct {
	Code      string          `json:"code"`
	Message   string          `json:"message"`
	Retryable bool            `json:"retryable"`
	Details   json.RawMessage `json:"details"`
}
