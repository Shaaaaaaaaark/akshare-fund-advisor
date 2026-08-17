// Package static serves the built React app and provides SPA fallback so
// client-side routes (/indices, /funds/:code, ...) resolve to index.html.
// It hosts pre-built assets only; it performs no business logic.
package static

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

// Handler serves files from dir. Requests that do not map to an existing file
// and are not API/asset requests fall back to index.html for the SPA router.
func Handler(dir string) http.Handler {
	fileServer := http.FileServer(http.Dir(dir))
	indexPath := filepath.Join(dir, "index.html")

	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		clean := filepath.Clean(r.URL.Path)
		candidate := filepath.Join(dir, clean)

		// Serve the real file when it exists and is inside the static dir.
		if within(dir, candidate) {
			if info, err := os.Stat(candidate); err == nil && !info.IsDir() {
				fileServer.ServeHTTP(w, r)
				return
			}
		}

		// Never SPA-fallback for asset-looking paths: return a real 404 so a
		// missing bundle is visible rather than masked by index.html.
		if strings.Contains(filepath.Base(clean), ".") {
			http.NotFound(w, r)
			return
		}

		http.ServeFile(w, r, indexPath)
	})
}

// within reports whether path is inside base, guarding against traversal.
func within(base, path string) bool {
	rel, err := filepath.Rel(base, path)
	if err != nil {
		return false
	}
	return !strings.HasPrefix(rel, "..")
}
