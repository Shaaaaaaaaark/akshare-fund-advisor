// Command server is the Go web backend (BFF) for the research dashboard.
//
// Responsibilities (docs/GO_PYTHON_CONTRACT.md): serve the built React app,
// aggregate Dashboard data through the standalone Python Data API, and
// reverse-proxy Agent requests (SSE) to the Python Agent API. The Dashboard
// path has no dependency on Agent or MCP services.
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
	"github.com/akshare-fund-advisor/web-backend/internal/dataapi"
	"github.com/akshare-fund-advisor/web-backend/internal/proxy"
	"github.com/akshare-fund-advisor/web-backend/internal/static"
)

type config struct {
	addr        string
	dataAPIURL  string
	agentAPIURL string
	staticDir   string
	universe    []string
	years       int
	concurrency int
	dataTimeout time.Duration
}

func loadConfig() config {
	return config{
		addr:        envStr("WEB_BACKEND_ADDR", ":8080"),
		dataAPIURL:  envStr("DATA_API_URL", "http://data-api:8003"),
		agentAPIURL: envStr("AGENT_API_URL", "http://agent-api:8000"),
		staticDir:   envStr("WEB_STATIC_DIR", "web/dist"),
		universe: envList("DASHBOARD_INDEX_UNIVERSE",
			[]string{"沪深300", "中证500", "中证1000", "上证50", "创业板50", "中证800"}),
		years:       envInt("DASHBOARD_INDEX_YEARS", 10),
		concurrency: envInt("DASHBOARD_CONCURRENCY", 2),
		// Keep transport headroom above the Python data operation's deadline so
		// the API can return a typed timeout envelope instead of being canceled.
		dataTimeout: time.Duration(
			envInt("DATA_API_TIMEOUT_SECONDS", 90),
		) * time.Second,
	}
}

func main() {
	cfg := loadConfig()

	dataClient := dataapi.New(cfg.dataAPIURL, cfg.dataTimeout)
	board := dashboard.NewService(dataClient, cfg.universe, cfg.years, cfg.concurrency)

	agentProxy, err := proxy.New(cfg.agentAPIURL)
	if err != nil {
		log.Fatalf("agent proxy: %v", err)
	}

	mux := http.NewServeMux()

	// Local liveness of the Go process itself.
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// Dashboard data path: Go calls the standalone Data API. No Agent, MCP
	// protocol, model, or financial computation participates in this path.
	// The bare path serves the board; the subtree path serves index detail.
	indicesHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		rest := strings.TrimPrefix(r.URL.Path, "/api/dashboard/indices")
		rest = strings.Trim(rest, "/")
		ctx, cancel := context.WithTimeout(r.Context(), cfg.dataTimeout+5*time.Second)
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

	fundsHandler := func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		rest := strings.TrimPrefix(r.URL.Path, "/api/dashboard/funds")
		rest = strings.Trim(rest, "/")
		ctx, cancel := context.WithTimeout(r.Context(), cfg.dataTimeout+5*time.Second)
		defer cancel()

		if rest == "search" {
			query := strings.TrimSpace(r.URL.Query().Get("query"))
			if query == "" {
				http.Error(w, "query is required", http.StatusBadRequest)
				return
			}
			limit := atoiDefault(r.URL.Query().Get("limit"), 10)
			if limit < 1 || limit > 20 {
				http.Error(w, "limit must be between 1 and 20", http.StatusBadRequest)
				return
			}
			writeJSON(w, http.StatusOK, board.FundSearch(ctx, query, limit))
			return
		}
		if rest == "" {
			http.Error(w, "fund path is required", http.StatusBadRequest)
			return
		}

		fund, err := url.PathUnescape(rest)
		if err != nil {
			http.Error(w, "bad fund path", http.StatusBadRequest)
			return
		}
		years := atoiDefault(r.URL.Query().Get("years"), 3)
		if years != 1 && years != 3 && years != 5 {
			http.Error(w, "years must be 1, 3 or 5", http.StatusBadRequest)
			return
		}
		maxPoints := atoiDefault(r.URL.Query().Get("max_points"), 600)
		if maxPoints < 50 || maxPoints > 3000 {
			http.Error(w, "max_points must be between 50 and 3000", http.StatusBadRequest)
			return
		}
		writeJSON(w, http.StatusOK, board.ETFDetail(ctx, fund, years, maxPoints))
	}
	mux.HandleFunc("/api/dashboard/funds", fundsHandler)
	mux.HandleFunc("/api/dashboard/funds/", fundsHandler)

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
		log.Printf("web-backend listening on %s (data_api=%s agent=%s static=%s)",
			cfg.addr, cfg.dataAPIURL, cfg.agentAPIURL, cfg.staticDir)
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
