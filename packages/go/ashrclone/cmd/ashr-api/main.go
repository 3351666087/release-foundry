package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strings"
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
	identityRuntime, err := productionIdentityRuntime(context.Background())
	if err != nil {
		log.Fatalf("configure identity runtime: %v", err)
	}
	if identityRuntime.close != nil {
		defer func() {
			if err := identityRuntime.close(); err != nil {
				log.Printf("close identity runtime: %v", err)
			}
		}()
	}
	var githubOAuth *ashrclone.GitHubOAuthService
	var googleOAuth *ashrclone.OAuthService
	if identityRuntime.mode == ashrclone.IdentityRuntimeMemory {
		identityBridge := ashrclone.UnifiedIdentityOAuthBridge{Identity: identityRuntime.unifiedIdentity}
		githubOAuth, err = ashrclone.NewGitHubOAuthServiceFromEnv(ashrclone.GitHubOAuthEnvRuntimeOptions{
			LookupEnv: os.LookupEnv, IdentityBridge: identityBridge, Identity: identityRuntime.unifiedIdentity,
		})
		if err != nil {
			log.Fatalf("configure GitHub OAuth: %v", err)
		}
		googleOAuth, err = ashrclone.NewGoogleOAuthServiceFromEnv(ashrclone.GoogleOAuthEnvRuntimeOptions{
			LookupEnv: os.LookupEnv, IdentityBridge: identityBridge, Identity: identityRuntime.unifiedIdentity,
		})
		if err != nil {
			log.Fatalf("configure Google OAuth: %v", err)
		}
	}
	oauthProviders := map[string]*ashrclone.OAuthService{}
	if googleOAuth != nil {
		oauthProviders["google"] = googleOAuth
	}
	identitySessions := identityRuntime.identitySessions
	if identityRuntime.mode == ashrclone.IdentityRuntimeMemory &&
		strings.EqualFold(strings.TrimSpace(os.Getenv("ASHR_IDENTITY_DEV_SESSION_ENABLED")), "true") {
		identitySessions = ashrclone.LocalhostDevIdentityHTTPSessionResolver{
			Enabled:   true,
			AccountID: os.Getenv("ASHR_IDENTITY_DEV_ACCOUNT_ID"),
			ActorID:   os.Getenv("ASHR_IDENTITY_DEV_ACTOR_ID"),
			SessionID: os.Getenv("ASHR_IDENTITY_DEV_SESSION_ID"),
		}
	}
	log.Printf("ashr Go control plane listening on %s with backend %s", addr, selection.Name)
	server := &http.Server{
		Addr:              addr,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
		Handler: ashrclone.NewHTTPServerWithOptions(selection.Backend, ashrclone.HTTPServerOptions{
			BackendName:                        selection.Name,
			BackendReady:                       selection.Ready,
			PaymentReconciliation:              selection.PaymentReconciliation,
			PaymentDomain:                      selection.PaymentDomain,
			UnifiedIdentity:                    identityRuntime.unifiedIdentity,
			IdentityLifecycle:                  identityRuntime.identityLifecycle,
			IdentitySessions:                   identitySessions,
			IdentityVerification:               identityRuntime.verification,
			IdentityVerificationResponsePolicy: identityRuntime.verificationResponsePolicy,
			IdentitySessionReceiptTransport:    identityRuntime.sessionReceiptTransport,
			OAuthProviders:                     oauthProviders,
			GitHubOAuth:                        githubOAuth,
		}),
	}
	if err := server.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}
