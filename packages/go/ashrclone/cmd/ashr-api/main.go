package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/ashr-labs/ashr/packages/go/ashrclone"
)

func main() {
	addr := os.Getenv("ASHR_GO_API_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8787"
	}
	selection, err := ashrclone.NewBackendFromEnv()
	if err != nil {
		log.Fatal(err)
	}
	if selection.Migrate != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
		defer cancel()
		if err := selection.Migrate(ctx); err != nil {
			log.Fatalf("migrate backend %s: %v", selection.Name, err)
		}
		selection.Ready = true
	}
	if selection.Close != nil {
		defer func() {
			if err := selection.Close(); err != nil {
				log.Printf("close backend: %v", err)
			}
		}()
	}
	log.Printf("ashr Go control plane listening on %s with backend %s", addr, selection.Name)
	if err := http.ListenAndServe(addr, ashrclone.NewHTTPServerWithOptions(selection.Backend, ashrclone.HTTPServerOptions{BackendName: selection.Name, BackendReady: selection.Ready})); err != nil {
		log.Fatal(err)
	}
}
