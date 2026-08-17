// Package mcp implements a minimal client for the Python Fund/Web MCP servers.
//
// The servers run FastMCP in stateless streamable-HTTP mode
// (stateless_http=True, json_response=True) at a fixed "/mcp" path. In this
// mode every request is a self-contained JSON-RPC POST: no session id, no SSE
// framing for tool calls, plain "application/json" responses. This client
// therefore does not implement the full MCP session lifecycle; it issues a
// single "tools/call" request and reads back the ToolEnvelope unchanged.
//
// Contract (docs/GO_PYTHON_CONTRACT.md): Go never recomputes, rounds,
// interpolates or synthesizes any market number. The ToolEnvelope and its
// data / data_audit / frame_sha256 fields are carried as json.RawMessage and
// passed through verbatim.
package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Envelope mirrors src/fund_advisor_mcp/fund/schemas.py::ToolEnvelope.
//
// Only the few fields the BFF reads for display (tool, ok, error) are typed.
// Everything that carries market facts or audit evidence stays as
// json.RawMessage so it is passed through byte-for-byte, per the contract.
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

// ToolError mirrors ToolError in the Python schema.
type ToolError struct {
	Code      string          `json:"code"`
	Message   string          `json:"message"`
	Retryable bool            `json:"retryable"`
	Details   json.RawMessage `json:"details"`
}

// Client calls a single MCP server over stateless streamable-HTTP.
type Client struct {
	endpoint string
	http     *http.Client
}

// New returns a Client for the given "/mcp" endpoint URL.
func New(endpoint string, timeout time.Duration) *Client {
	return &Client{
		endpoint: endpoint,
		http:     &http.Client{Timeout: timeout},
	}
}

type rpcRequest struct {
	JSONRPC string `json:"jsonrpc"`
	ID      int    `json:"id"`
	Method  string `json:"method"`
	Params  any    `json:"params"`
}

type toolCallParams struct {
	Name      string         `json:"name"`
	Arguments map[string]any `json:"arguments"`
}

type rpcResponse struct {
	Error  *rpcError       `json:"error"`
	Result *toolCallResult `json:"result"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// toolCallResult mirrors the MCP tools/call result. FastMCP with
// json_response=True returns the ToolEnvelope under structuredContent; some
// versions nest it one level as {"result": ...}. structuredContent is decoded
// lazily so both shapes are handled without re-serializing the envelope.
type toolCallResult struct {
	StructuredContent json.RawMessage `json:"structuredContent"`
	IsError           bool            `json:"isError"`
}

// CallTool invokes an MCP tool and returns the raw ToolEnvelope bytes together
// with a minimally-typed view. The raw bytes are what the BFF passes through to
// the browser; the typed view is only for status mapping and field selection.
func (c *Client) CallTool(
	ctx context.Context,
	tool string,
	arguments map[string]any,
) (json.RawMessage, *Envelope, error) {
	reqBody, err := json.Marshal(rpcRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  "tools/call",
		Params:  toolCallParams{Name: tool, Arguments: arguments},
	})
	if err != nil {
		return nil, nil, fmt.Errorf("marshal request: %w", err)
	}

	httpReq, err := http.NewRequestWithContext(
		ctx, http.MethodPost, c.endpoint, bytes.NewReader(reqBody),
	)
	if err != nil {
		return nil, nil, fmt.Errorf("build request: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	// Stateless streamable-HTTP still requires the client to advertise it can
	// accept either response encoding.
	httpReq.Header.Set("Accept", "application/json, text/event-stream")

	resp, err := c.http.Do(httpReq)
	if err != nil {
		return nil, nil, fmt.Errorf("call %s: %w", tool, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, nil, fmt.Errorf("read %s response: %w", tool, err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, nil, fmt.Errorf(
			"mcp %s http %d: %s", tool, resp.StatusCode, truncate(body, 200),
		)
	}

	var rpc rpcResponse
	if err := json.Unmarshal(body, &rpc); err != nil {
		return nil, nil, fmt.Errorf(
			"decode %s response: %w (body: %s)", tool, err, truncate(body, 200),
		)
	}
	if rpc.Error != nil {
		return nil, nil, fmt.Errorf(
			"mcp %s error %d: %s", tool, rpc.Error.Code, rpc.Error.Message,
		)
	}
	if rpc.Result == nil || len(rpc.Result.StructuredContent) == 0 {
		return nil, nil, fmt.Errorf("mcp %s returned no structured content", tool)
	}
	if rpc.Result.IsError {
		return nil, nil, fmt.Errorf("mcp %s reported tool execution error", tool)
	}

	rawEnvelope := unwrapEnvelope(rpc.Result.StructuredContent)

	var env Envelope
	if err := json.Unmarshal(rawEnvelope, &env); err != nil {
		return nil, nil, fmt.Errorf("decode %s envelope: %w", tool, err)
	}
	return rawEnvelope, &env, nil
}

// Healthcheck confirms the MCP endpoint accepts the JSON-RPC initialize call.
func (c *Client) Healthcheck(ctx context.Context) error {
	reqBody, _ := json.Marshal(rpcRequest{
		JSONRPC: "2.0",
		ID:      1,
		Method:  "initialize",
		Params: map[string]any{
			"protocolVersion": "2025-06-18",
			"capabilities":    map[string]any{},
			"clientInfo":      map[string]any{"name": "web-backend", "version": "0"},
		},
	})
	httpReq, err := http.NewRequestWithContext(
		ctx, http.MethodPost, c.endpoint, bytes.NewReader(reqBody),
	)
	if err != nil {
		return err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("Accept", "application/json, text/event-stream")
	resp, err := c.http.Do(httpReq)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("mcp initialize http %d", resp.StatusCode)
	}
	return nil
}

// unwrapEnvelope tolerates the optional {"result": <envelope>} nesting that some
// FastMCP versions add around structuredContent. It only unwraps when the outer
// object is exactly a single "result" key, so a real ToolEnvelope (which also
// has many keys) is never misread.
func unwrapEnvelope(structured json.RawMessage) json.RawMessage {
	var probe map[string]json.RawMessage
	if err := json.Unmarshal(structured, &probe); err != nil {
		return structured
	}
	if inner, ok := probe["result"]; ok && len(probe) == 1 {
		return inner
	}
	return structured
}

func truncate(b []byte, n int) string {
	if len(b) <= n {
		return string(b)
	}
	return string(b[:n])
}
