package dashboard

import (
	"context"
	"encoding/json"
	"time"

	"github.com/akshare-fund-advisor/web-backend/internal/facts"
)

const (
	fundSearchTool   = "fund_search"
	etfDashboardTool = "etf_dashboard"
)

// FundSearchResponse passes the audited fund_search envelope through unchanged.
type FundSearchResponse struct {
	Query    string          `json:"query"`
	Meta     DatasetMeta     `json:"meta"`
	Envelope json.RawMessage `json:"envelope,omitempty"`
}

// ETFDetail passes the audited etf_dashboard envelope through unchanged.
type ETFDetail struct {
	Fund     string          `json:"fund"`
	Meta     DatasetMeta     `json:"meta"`
	Envelope json.RawMessage `json:"envelope,omitempty"`
}

// FundSearch resolves user-entered names or codes without choosing ambiguous
// share classes in Go.
func (s *Service) FundSearch(ctx context.Context, query string, limit int) FundSearchResponse {
	raw, env, err := s.fund.CallTool(ctx, fundSearchTool, map[string]any{
		"query": query,
		"limit": limit,
	})
	if err != nil {
		return FundSearchResponse{
			Query: query,
			Meta:  transportFailureMeta(fundSearchTool),
		}
	}
	return FundSearchResponse{
		Query:    query,
		Meta:     envelopeMeta(env, fundSearchTool, ""),
		Envelope: raw,
	}
}

// ETFDetail returns only Skill-produced ETF dashboard data. Go does not
// resample chart_series, calculate summaries or alter recent rows.
func (s *Service) ETFDetail(
	ctx context.Context,
	fund string,
	years int,
	maxPoints int,
) ETFDetail {
	raw, env, err := s.fund.CallTool(ctx, etfDashboardTool, map[string]any{
		"fund":       fund,
		"years":      years,
		"max_points": maxPoints,
	})
	if err != nil {
		return ETFDetail{
			Fund: fund,
			Meta: transportFailureMeta(etfDashboardTool),
		}
	}

	asOf := ""
	if env.OK {
		var view struct {
			Summary struct {
				LatestDate string `json:"latest_date"`
			} `json:"summary"`
		}
		if json.Unmarshal(env.Data, &view) == nil {
			asOf = view.Summary.LatestDate
		}
	}
	return ETFDetail{
		Fund:     fund,
		Meta:     envelopeMeta(env, etfDashboardTool, asOf),
		Envelope: raw,
	}
}

func transportFailureMeta(tool string) DatasetMeta {
	return DatasetMeta{
		Status:      StatusUnavailable,
		SourceTools: []string{tool},
		QueriedAt:   time.Now().UTC().Format(time.RFC3339),
	}
}

func envelopeMeta(env *facts.Envelope, tool string, asOf string) DatasetMeta {
	meta := DatasetMeta{
		AsOf:        asOf,
		QueriedAt:   env.QueriedAt,
		Status:      mapStatus(env),
		SourceTools: []string{tool},
		AuditRefs:   frameHashes(env.DataAudit),
		Warnings:    nonEmpty(env.DataWarnings),
	}
	if env.Error != nil {
		if b, err := json.Marshal(env.Error); err == nil {
			meta.Error = b
		}
	}
	return meta
}
