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
	log.Printf("ashr Go control plane listening on %s", addr)
	if err := http.ListenAndServe(addr, ashrclone.NewHTTPHandler(ashrclone.NewMemoryService())); err != nil {
		log.Fatal(err)
	}
}
