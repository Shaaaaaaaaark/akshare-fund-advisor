// Command server is the Go web backend (BFF) for the research dashboard.
//
// Responsibilities (docs/GO_PYTHON_CONTRACT.md): serve the built React app,
// aggregate Dashboard data by calling the Python Fund MCP as an MCP client, and
// reverse-proxy Agent requests (SSE) to the Python Agent API. It performs no
// financial computation and passes ToolEnvelope audit fields through unchanged.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/akshare-fund-advisor/web-backend/internal/dashboard"
	"github.com/akshare-fund-advisor/web-backend/internal/mcp"
	"github.com/akshare-fund-advisor/web-backend/internal/proxy"
	"github.com/akshare-fund-advisor/web-backend/internal/static"
)

type config struct {
	addr        string
	fundMCPURL  string
	agentAPIURL string
	staticDir   string
	universe    []string
	years       int
	concurrency int
	mcpTimeout  time.Duration
}

func loadConfig() config {
	return config{
		addr:        envStr("WEB_BACKEND_ADDR", ":8080"),
		fundMCPURL:  envStr("FUND_MCP_URL", "http://fund-advisor-mcp:8001/mcp"),
		agentAPIURL: envStr("AGENT_API_URL", "http://agent-api:8000"),
		staticDir:   envStr("WEB_STATIC_DIR", "web/dist"),
		universe: envList("DASHBOARD_INDEX_UNIVERSE",
			[]string{"沪深300", "中证500", "中证1000", "上证50", "创业板50", "中证800"}),
		years:       envInt("DASHBOARD_INDEX_YEARS", 10),
		concurrency: envInt("DASHBOARD_CONCURRENCY", 2),
		mcpTimeout:  time.Duration(envInt("MCP_TIMEOUT_SECONDS", 60)) * time.Second,
	}
}

func main() {
	cfg := loadConfig()

	fundClient := mcp.New(cfg.fundMCPURL, cfg.mcpTimeout)
	board := dashboard.NewService(fundClient, cfg.universe, cfg.years, cfg.concurrency)

	agentProxy, err := proxy.New(cfg.agentAPIURL)
	if err != nil {
		log.Fatalf("agent proxy: %v", err)
	}

	mux := http.NewServeMux()

	// Local liveness of the Go process itself.
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// Dashboard data path: Go acts as MCP client. No model, no computation.
	// The bare path serves the board; the subtree path serves index detail.
	indicesHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		rest := strings.TrimPrefix(r.URL.Path, "/api/dashboard/indices")
		rest = strings.Trim(rest, "/")
		ctx, cancel := context.WithTimeout(r.Context(), cfg.mcpTimeout+5*time.Second)
		defer cancel()
		if rest == "" {
			writeJSON(w, http.StatusOK, board.Indices(ctx))
			return
		}
		index, err := url.PathUnescape(rest)
		if err != nil {
			http.Error(w, "bad index path", http.StatusBadRequest)
			return
		}
		years := atoiDefault(r.URL.Query().Get("years"), 0)
		maxPoints := atoiDefault(r.URL.Query().Get("max_points"), 0)
		writeJSON(w, http.StatusOK, board.IndexDetail(ctx, index, years, maxPoints))
	}
	mux.HandleFunc("/api/dashboard/indices", indicesHandler)
	mux.HandleFunc("/api/dashboard/indices/", indicesHandler)

	// Agent path: reverse-proxy SSE to Python Agent API, frames verbatim.
	mux.Handle("/api/chat/", agentProxy)
	mux.Handle("/api/sessions", agentProxy)
	mux.Handle("/api/sessions/", agentProxy)

	// Static React app with SPA fallback for all remaining routes.
	mux.Handle("/", static.Handler(cfg.staticDir))

	srv := &http.Server{
		Addr:              cfg.addr,
		Handler:           mux,
		ReadHeaderTimeout: 10 * time.Second,
	}

	go func() {
		log.Printf("web-backend listening on %s (fund_mcp=%s agent=%s static=%s)",
			cfg.addr, cfg.fundMCPURL, cfg.agentAPIURL, cfg.staticDir)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("listen: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(shutdownCtx); err != nil {
		log.Printf("graceful shutdown: %v", err)
	}
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func envStr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

func envInt(key string, fallback int) int {
	return atoiDefault(os.Getenv(key), fallback)
}

func envList(key string, fallback []string) []string {
	raw := strings.TrimSpace(os.Getenv(key))
	if raw == "" {
		return fallback
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		if trimmed := strings.TrimSpace(p); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	if len(out) == 0 {
		return fallback
	}
	return out
}

func atoiDefault(s string, fallback int) int {
	if v, err := strconv.Atoi(strings.TrimSpace(s)); err == nil {
		return v
	}
	return fallback
}
