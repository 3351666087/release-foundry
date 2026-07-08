package main

import (
	"log"
	"net/http"
	"os"

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
	if selection.Close != nil {
		defer func() {
			if err := selection.Close(); err != nil {
				log.Printf("close backend: %v", err)
			}
		}()
	}
	log.Printf("ashr Go control plane listening on %s with backend %s", addr, selection.Name)
	if err := http.ListenAndServe(addr, ashrclone.NewHTTPServerWithOptions(selection.Backend, ashrclone.HTTPServerOptions{BackendName: selection.Name})); err != nil {
		log.Fatal(err)
	}
}
