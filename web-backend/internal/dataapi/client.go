// Package dataapi calls the standalone Python market-data REST API.
package dataapi

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/akshare-fund-advisor/web-backend/internal/facts"
)

// Client is the Dashboard-only REST client. It knows nothing about MCP or the
// Agent graph and returns audited envelopes without re-serializing them.
type Client struct {
	baseURL string
	http    *http.Client
}

func New(baseURL string, timeout time.Duration) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http:    &http.Client{Timeout: timeout},
	}
}

// CallTool keeps the Dashboard service transport-agnostic while mapping its
// three registered data operations onto explicit REST resources.
func (c *Client) CallTool(
	ctx context.Context,
	tool string,
	arguments map[string]any,
) (json.RawMessage, *facts.Envelope, error) {
	path, query, err := route(tool, arguments)
	if err != nil {
		return nil, nil, err
	}
	endpoint := c.baseURL + path
	if encoded := query.Encode(); encoded != "" {
		endpoint += "?" + encoded
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, nil, fmt.Errorf("build data api request: %w", err)
	}
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		return nil, nil, fmt.Errorf("call data api %s: %w", tool, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, nil, fmt.Errorf("read data api %s: %w", tool, err)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, nil, fmt.Errorf(
			"data api %s http %d: %s",
			tool,
			resp.StatusCode,
			truncate(body, 200),
		)
	}

	var envelope facts.Envelope
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, nil, fmt.Errorf("decode data api %s envelope: %w", tool, err)
	}
	return json.RawMessage(body), &envelope, nil
}

func (c *Client) Healthcheck(ctx context.Context) error {
	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		c.baseURL+"/health",
		nil,
	)
	if err != nil {
		return err
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("data api health http %d", resp.StatusCode)
	}
	return nil
}

func route(tool string, arguments map[string]any) (string, url.Values, error) {
	query := make(url.Values)
	switch tool {
	case "fund_search":
		value, err := stringArgument(arguments, "query")
		if err != nil {
			return "", nil, err
		}
		query.Set("query", value)
		query.Set("limit", strconv.Itoa(intArgument(arguments, "limit", 10)))
		return "/v1/funds/search", query, nil
	case "etf_dashboard":
		fund, err := stringArgument(arguments, "fund")
		if err != nil {
			return "", nil, err
		}
		query.Set("years", strconv.Itoa(intArgument(arguments, "years", 3)))
		query.Set(
			"max_points",
			strconv.Itoa(intArgument(arguments, "max_points", 600)),
		)
		return "/v1/etfs/" + url.PathEscape(fund), query, nil
	case "index_valuation":
		index, err := stringArgument(arguments, "index")
		if err != nil {
			return "", nil, err
		}
		query.Set("years", strconv.Itoa(intArgument(arguments, "years", 10)))
		query.Set(
			"max_points",
			strconv.Itoa(intArgument(arguments, "max_points", 600)),
		)
		return "/v1/indices/" + url.PathEscape(index), query, nil
	default:
		return "", nil, fmt.Errorf("unsupported dashboard data operation %q", tool)
	}
}

func stringArgument(arguments map[string]any, key string) (string, error) {
	value, ok := arguments[key].(string)
	if !ok || strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("data api argument %q is required", key)
	}
	return value, nil
}

func intArgument(arguments map[string]any, key string, fallback int) int {
	switch value := arguments[key].(type) {
	case int:
		return value
	case float64:
		return int(value)
	default:
		return fallback
	}
}

func truncate(body []byte, limit int) string {
	if len(body) <= limit {
		return string(body)
	}
	return string(body[:limit])
}
