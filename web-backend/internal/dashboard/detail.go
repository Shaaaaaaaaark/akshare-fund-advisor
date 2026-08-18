package dashboard

import (
	"context"
	"encoding/json"
	"time"
)

// IndexDetail is the payload of GET /api/dashboard/indices/{index}. The raw
// ToolEnvelope is passed through verbatim under "envelope" so the frontend has
// chart_series, reference_lines, window_statistics, source_observations,
// displayed_points and data_audit exactly as the tool produced them. Go adds
// only DatasetMeta; it never resamples or backfills chart points.
type IndexDetail struct {
	Index    string          `json:"index"`
	Meta     DatasetMeta     `json:"meta"`
	Envelope json.RawMessage `json:"envelope"`
}

// IndexDetail queries index_valuation for a single index at the requested
// window and returns the raw envelope plus metadata.
func (s *Service) IndexDetail(ctx context.Context, index string, years, maxPoints int) IndexDetail {
	if years == 0 {
		years = s.years
	}
	args := map[string]any{"index": index, "years": years}
	if maxPoints > 0 {
		args["max_points"] = maxPoints
	}

	raw, env, err := s.fund.CallTool(ctx, indexValuationTool, args)
	if err != nil {
		return IndexDetail{
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
		if b, mErr := json.Marshal(env.Error); mErr == nil {
			meta.Error = b
		}
	}
	if env.OK {
		var view summaryView
		if json.Unmarshal(env.Data, &view) == nil {
			meta.AsOf = view.asOf()
		}
	}

	return IndexDetail{Index: index, Meta: meta, Envelope: raw}
}
