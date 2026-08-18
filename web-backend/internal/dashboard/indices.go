package dashboard

import (
	"context"
	"encoding/json"
	"sort"
	"sync"
	"time"

	"github.com/akshare-fund-advisor/web-backend/internal/facts"
)

// indexValuationTool is the audited data operation this board consumes.
const indexValuationTool = "index_valuation"

type ToolCaller interface {
	CallTool(
		ctx context.Context,
		tool string,
		arguments map[string]any,
	) (json.RawMessage, *facts.Envelope, error)
}

// Service builds dashboard responses from the standalone Data API. It holds no
// mutable market state; every request reads live from the tool.
type Service struct {
	fund        ToolCaller
	universe    []string
	years       int
	concurrency int
}

// NewService wires the board to an audited data caller and configured universe.
func NewService(fund ToolCaller, universe []string, years, concurrency int) *Service {
	if concurrency < 1 {
		concurrency = 1
	}
	if years == 0 {
		years = 10
	}
	return &Service{
		fund:        fund,
		universe:    universe,
		years:       years,
		concurrency: concurrency,
	}
}

// Indices queries index_valuation for each configured index using bounded
// concurrency (never an unbounded fan-out) and assembles the board. One failing
// index yields an unavailable row while the others render; the page status is
// then partial.
func (s *Service) Indices(ctx context.Context) IndicesResponse {
	rows := make([]IndexRow, len(s.universe))
	sem := make(chan struct{}, s.concurrency)
	var wg sync.WaitGroup

	for i, index := range s.universe {
		wg.Add(1)
		go func(i int, index string) {
			defer wg.Done()
			sem <- struct{}{}
			defer func() { <-sem }()
			rows[i] = s.indexRow(ctx, index)
		}(i, index)
	}
	wg.Wait()

	statuses := make([]DataStatus, len(rows))
	for i, r := range rows {
		statuses[i] = r.Meta.Status
	}

	// Present a stable order: successful rows keep configured order; failed and
	// stale rows sink to the bottom so they never sit among sortable values.
	sort.SliceStable(rows, func(a, b int) bool {
		return statusRank(rows[a].Meta.Status) < statusRank(rows[b].Meta.Status)
	})

	return IndicesResponse{Status: rollUp(statuses), Rows: rows}
}

func statusRank(s DataStatus) int {
	switch s {
	case StatusAvailable:
		return 0
	case StatusPartial:
		return 1
	case StatusStale:
		return 2
	default:
		return 3
	}
}

func (s *Service) indexRow(ctx context.Context, index string) IndexRow {
	raw, env, err := s.fund.CallTool(ctx, indexValuationTool, map[string]any{
		"index": index,
		"years": s.years,
	})
	if err != nil {
		// Transport-level failure: no envelope to pass through. This is an
		// upstream failure, not "index does not exist".
		return IndexRow{
			Index: index,
			Meta: DatasetMeta{
				Status:      StatusUnavailable,
				SourceTools: []string{indexValuationTool},
				QueriedAt:   time.Now().UTC().Format(time.RFC3339),
			},
		}
	}

	meta := DatasetMeta{
		QueriedAt:   env.QueriedAt,
		Status:      mapStatus(env),
		SourceTools: []string{indexValuationTool},
		AuditRefs:   frameHashes(env.DataAudit),
		Warnings:    nonEmpty(env.DataWarnings),
	}
	if env.Error != nil {
		// Pass the original ToolError through verbatim (keeps error.code).
		if b, mErr := json.Marshal(env.Error); mErr == nil {
			meta.Error = b
		}
	}

	row := IndexRow{Index: index, Meta: meta}
	if env.OK {
		fillFromData(&row, raw, env.Data)
	}
	return row
}

// summaryView is a read-only projection of the scalar display fields the board
// shows. It intentionally omits chart_series, reference_lines and
// window_statistics: those are for the detail endpoint and are never resampled
// or recomputed here.
type summaryView struct {
	Summary struct {
		PETTM *Metric `json:"pe_ttm"`
		PB    *Metric `json:"pb"`
	} `json:"summary"`
	Charts struct {
		PETTM struct {
			LatestDate string `json:"latest_date"`
		} `json:"pe_ttm"`
		PB struct {
			LatestDate string `json:"latest_date"`
		} `json:"pb"`
		IndexPoints struct {
			Current *float64 `json:"current"`
		} `json:"index_points"`
	} `json:"charts"`
	Lookback struct {
		LatestDate string `json:"latest_date"`
	} `json:"lookback"`
}

// fillFromData copies scalar display fields out of the envelope's data object.
// It is a read-only selection (permitted by contract §4); it computes nothing.
func fillFromData(row *IndexRow, _ json.RawMessage, data json.RawMessage) {
	if len(data) == 0 {
		return
	}
	var view summaryView
	if err := json.Unmarshal(data, &view); err != nil {
		return
	}
	row.PETTM = view.Summary.PETTM
	row.PB = view.Summary.PB
	row.LatestPoint = view.Charts.IndexPoints.Current
	// as_of is the tool's own latest data date, never the server clock.
	row.Meta.AsOf = view.asOf()
}

func (view summaryView) asOf() string {
	for _, value := range []string{
		view.Charts.PETTM.LatestDate,
		view.Charts.PB.LatestDate,
		view.Lookback.LatestDate,
	} {
		if value != "" {
			return value
		}
	}
	return ""
}

// frameHashes extracts frame_sha256 values from data_audit for auditability.
// It reads existing evidence; it does not create or alter any hash.
func frameHashes(dataAudit json.RawMessage) []string {
	if len(dataAudit) == 0 {
		return nil
	}
	var entries []struct {
		FrameSHA256 string `json:"frame_sha256"`
	}
	if err := json.Unmarshal(dataAudit, &entries); err != nil {
		return nil
	}
	var hashes []string
	for _, e := range entries {
		if e.FrameSHA256 != "" {
			hashes = append(hashes, e.FrameSHA256)
		}
	}
	return hashes
}

// nonEmpty returns the raw JSON only when it carries a non-empty array/object,
// so an empty [] does not clutter the response.
func nonEmpty(raw json.RawMessage) json.RawMessage {
	trimmed := string(raw)
	if trimmed == "" || trimmed == "[]" || trimmed == "null" || trimmed == "{}" {
		return nil
	}
	return raw
}
