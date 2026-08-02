package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

func main() {
	addr := os.Getenv("RELEASEFOUNDRY_GO_API_ADDR")
	if addr == "" {
		addr = "127.0.0.1:8787"
	}
	selection, err := releasefoundry.NewBackendFromEnv()
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
	var githubOAuth *releasefoundry.GitHubOAuthService
	var googleOAuth *releasefoundry.OAuthService
	if identityRuntime.mode == releasefoundry.IdentityRuntimeMemory {
		identityBridge := releasefoundry.UnifiedIdentityOAuthBridge{Identity: identityRuntime.unifiedIdentity}
		githubOAuth, err = releasefoundry.NewGitHubOAuthServiceFromEnv(releasefoundry.GitHubOAuthEnvRuntimeOptions{
			LookupEnv: os.LookupEnv, IdentityBridge: identityBridge, Identity: identityRuntime.unifiedIdentity,
		})
		if err != nil {
			log.Fatalf("configure GitHub OAuth: %v", err)
		}
		googleOAuth, err = releasefoundry.NewGoogleOAuthServiceFromEnv(releasefoundry.GoogleOAuthEnvRuntimeOptions{
			LookupEnv: os.LookupEnv, IdentityBridge: identityBridge, Identity: identityRuntime.unifiedIdentity,
		})
		if err != nil {
			log.Fatalf("configure Google OAuth: %v", err)
		}
	}
	oauthProviders := map[string]*releasefoundry.OAuthService{}
	if googleOAuth != nil {
		oauthProviders["google"] = googleOAuth
	}
	identitySessions := identityRuntime.identitySessions
	if identityRuntime.mode == releasefoundry.IdentityRuntimeMemory &&
		strings.EqualFold(strings.TrimSpace(os.Getenv("RELEASEFOUNDRY_IDENTITY_DEV_SESSION_ENABLED")), "true") {
		identitySessions = releasefoundry.LocalhostDevIdentityHTTPSessionResolver{
			Enabled:   true,
			AccountID: os.Getenv("RELEASEFOUNDRY_IDENTITY_DEV_ACCOUNT_ID"),
			ActorID:   os.Getenv("RELEASEFOUNDRY_IDENTITY_DEV_ACTOR_ID"),
			SessionID: os.Getenv("RELEASEFOUNDRY_IDENTITY_DEV_SESSION_ID"),
		}
	}
	log.Printf("releasefoundry Go control plane listening on %s with backend %s", addr, selection.Name)
	serverOptions := identityHTTPServerOptions(identityRuntime, identitySessions)
	serverOptions.BackendName = selection.Name
	serverOptions.BackendReady = selection.Ready
	serverOptions.PaymentReconciliation = selection.PaymentReconciliation
	serverOptions.PaymentDomain = selection.PaymentDomain
	serverOptions.OAuthProviders = oauthProviders
	serverOptions.GitHubOAuth = githubOAuth
	serverOptions.ProviderDispatch = selection.ProviderDispatch
	server := &http.Server{
		Addr:              addr,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
		Handler:           releasefoundry.NewHTTPServerWithOptions(selection.Backend, serverOptions),
	}
	if err := server.ListenAndServe(); err != nil {
		log.Fatal(err)
	}
}

func identityHTTPServerOptions(
	runtime identityRuntime,
	sessions releasefoundry.IdentityHTTPSessionResolver,
) releasefoundry.HTTPServerOptions {
	options := releasefoundry.HTTPServerOptions{
		UnifiedIdentity:                    runtime.unifiedIdentity,
		IdentityLifecycle:                  runtime.identityLifecycle,
		IdentitySessions:                   sessions,
		IdentityVerification:               runtime.verification,
		IdentityVerificationResponsePolicy: runtime.verificationResponsePolicy,
		IdentitySessionReceiptTransport:    runtime.sessionReceiptTransport,
		IdentitySecurityService:            runtime.identitySecurityService,
		Tenancy:                            runtime.tenancy,
	}
	if intentTransport, ok := runtime.sessionReceiptTransport.(releasefoundry.IdentityBrowserVerificationIntentTransport); ok {
		options.IdentityBrowserVerificationIntents = intentTransport
	}
	if len(runtime.oauthFirstLogins) != 0 {
		if intentTransport, ok := runtime.sessionReceiptTransport.(releasefoundry.OAuthFirstLoginIntentTransport); ok {
			options.OAuthFirstLogins = make(
				map[string]*releasefoundry.OAuthFirstLoginService,
				len(runtime.oauthFirstLogins),
			)
			for provider, service := range runtime.oauthFirstLogins {
				options.OAuthFirstLogins[provider] = service
			}
			options.OAuthFirstLoginIntents = intentTransport
		}
	}
	if runtime.postgres != nil {
		options.UnifiedIdentityStore = runtime.postgres
		options.IdentitySecurity = runtime.postgres
		options.IdentitySecurityTickets = runtime.postgres
	}
	return options
}
