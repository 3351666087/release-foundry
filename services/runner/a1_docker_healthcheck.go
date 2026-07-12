package main

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

func main() {
	url := "http://127.0.0.1:8787/healthz"
	if len(os.Args) > 1 {
		url = os.Args[1]
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "build healthcheck request: %v\n", err)
		os.Exit(2)
	}

	response, err := http.DefaultClient.Do(request)
	if err != nil {
		fmt.Fprintf(os.Stderr, "healthcheck request failed: %v\n", err)
		os.Exit(1)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		fmt.Fprintf(os.Stderr, "healthcheck returned HTTP %d\n", response.StatusCode)
		os.Exit(1)
	}

	if len(os.Args) > 2 {
		var payload struct {
			Status       string `json:"status"`
			Backend      string `json:"backend"`
			Ready        bool   `json:"ready"`
			BackendReady bool   `json:"backend_ready"`
			LocalOnly    bool   `json:"local_only"`
		}
		if err := json.NewDecoder(response.Body).Decode(&payload); err != nil {
			fmt.Fprintf(os.Stderr, "decode healthcheck response: %v\n", err)
			os.Exit(1)
		}
		expectedBackend := strings.TrimSpace(os.Args[2])
		if payload.Status != "ok" || payload.Backend != expectedBackend || !payload.Ready || !payload.BackendReady || payload.LocalOnly {
			fmt.Fprintf(
				os.Stderr,
				"healthcheck fail closed: status=%q backend=%q ready=%t backend_ready=%t local_only=%t\n",
				payload.Status,
				payload.Backend,
				payload.Ready,
				payload.BackendReady,
				payload.LocalOnly,
			)
			os.Exit(1)
		}
	}
}
