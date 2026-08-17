package dashboard

import (
	"strings"

	"github.com/akshare-fund-advisor/web-backend/internal/mcp"
)

// mapStatus maps a tool envelope to a display status per
// docs/GO_PYTHON_CONTRACT.md §5. Go does not invent severity: a successful
// envelope is available (or stale, if the tool itself flags staleness), and any
// error keeps the original error.code while surfacing as unavailable. The
// concrete codes are those documented in docs/ERROR_HANDLING.md §4.
func mapStatus(env *mcp.Envelope) DataStatus {
	if env == nil {
		return StatusUnavailable
	}
	if env.OK {
		return StatusAvailable
	}
	if env.Error == nil {
		return StatusUnavailable
	}
	if isStaleCode(env.Error.Code) {
		return StatusStale
	}
	// NOT_FOUND / AMBIGUOUS / UNSUPPORTED / UPSTREAM_ERROR and all Fund Advisor
	// error codes collapse to unavailable; the original code travels in the
	// passed-through error field so the frontend can distinguish them.
	return StatusUnavailable
}

// isStaleCode reports whether an error code denotes stale-but-present data,
// which the contract renders as "stale" rather than "unavailable".
func isStaleCode(code string) bool {
	upper := strings.ToUpper(code)
	switch upper {
	case "STALE_DATA", "STALE_OR_INVALID_DATA":
		return true
	}
	return strings.Contains(upper, "STALE")
}

// rollUp computes the page-level status from the per-index statuses:
//   - all available            -> available
//   - all hard-failed           -> unavailable
//   - some failed, some resolved -> partial (per M1: one index failing must not
//     fail the whole page)
//   - no failures but some stale -> stale (data is present but not fresh)
//
// not_implemented is treated as a hard failure for roll-up purposes.
func rollUp(statuses []DataStatus) DataStatus {
	if len(statuses) == 0 {
		return StatusUnavailable
	}
	available, stale, failed := 0, 0, 0
	for _, s := range statuses {
		switch s {
		case StatusAvailable:
			available++
		case StatusStale:
			stale++
		case StatusUnavailable, StatusNotImplemented:
			failed++
		}
	}
	if failed == len(statuses) {
		return StatusUnavailable
	}
	if failed > 0 {
		return StatusPartial
	}
	if stale > 0 {
		return StatusStale
	}
	if available == len(statuses) {
		return StatusAvailable
	}
	return StatusPartial
}
