// Package proxy reverse-proxies Agent API requests (including the SSE chat
// stream) to the Python service. Per docs/GO_PYTHON_CONTRACT.md §6 it forwards
// frames verbatim: it does not buffer the whole stream, reorder events, parse
// research conclusions, inject numbers, or rewrite gate results.
package proxy

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"strings"
)

// New returns a reverse proxy to the Agent API base URL. It streams responses
// (FlushInterval < 0 forces immediate flushing, which is required for SSE) and
// disables response buffering so text/event-stream frames reach the client as
// they are produced.
func New(agentBaseURL string) (*httputil.ReverseProxy, error) {
	target, err := url.Parse(agentBaseURL)
	if err != nil {
		return nil, err
	}

	rp := httputil.NewSingleHostReverseProxy(target)
	// Negative interval flushes each write immediately: mandatory for SSE.
	rp.FlushInterval = -1

	base := rp.Director
	rp.Director = func(r *http.Request) {
		base(r)
		// Preserve the upstream Host and keep the original path/query; the Agent
		// API already serves /api/... and /health.
		r.Host = target.Host
	}

	rp.ModifyResponse = func(resp *http.Response) error {
		// For event streams, make sure no intermediate cache buffers frames.
		if strings.HasPrefix(resp.Header.Get("Content-Type"), "text/event-stream") {
			resp.Header.Set("X-Accel-Buffering", "no")
			resp.Header.Set("Cache-Control", "no-cache")
		}
		return nil
	}

	return rp, nil
}
