package ashrclone

import (
	"context"
	"errors"
	"net/http"
	"strings"
)

type OAuthIdentityLinkResult struct {
	Credential IdentityCredentialDTO
	Created    bool
}

type OAuthIdentityBridge interface {
	LinkVerifiedOAuthCredential(context.Context, string, string, string, string) (OAuthIdentityLinkResult, error)
	ValidateOAuthCredentialUnlink(context.Context, string, string) error
	UnlinkOAuthCredential(context.Context, string, string, string) error
}

type UnifiedIdentityOAuthBridge struct {
	Identity *UnifiedIdentityService
}

func (bridge UnifiedIdentityOAuthBridge) LinkVerifiedOAuthCredential(
	_ context.Context,
	accountID string,
	provider string,
	rawProviderSubject string,
	actorID string,
) (OAuthIdentityLinkResult, error) {
	if bridge.Identity == nil {
		return OAuthIdentityLinkResult{}, newOAuthPublicError(http.StatusServiceUnavailable, "identity_service_unavailable", "canonical identity service is unavailable", nil)
	}
	providerID, err := oauthIdentityProvider(provider)
	if err != nil {
		return OAuthIdentityLinkResult{}, err
	}
	if strings.TrimSpace(rawProviderSubject) == "" {
		return OAuthIdentityLinkResult{}, newOAuthPublicError(http.StatusBadGateway, "oauth_identity_invalid", "provider returned an invalid identity", nil)
	}
	if _, err := bridge.Identity.EnsureAccount(accountID, actorID); err != nil {
		return OAuthIdentityLinkResult{}, oauthIdentityBridgeError(err)
	}
	credential, created, err := bridge.Identity.LinkCredentialWithStatus(accountID, LinkIdentityCredentialRequest{
		Credential: IdentityCredentialInput{
			Kind: IdentityCredentialOAuth, Provider: providerID,
			Identifier: rawProviderSubject, Verified: true,
		},
		ActorID: actorID,
	})
	if err != nil {
		return OAuthIdentityLinkResult{}, oauthIdentityBridgeError(err)
	}
	return OAuthIdentityLinkResult{Credential: credential, Created: created}, nil
}

func (bridge UnifiedIdentityOAuthBridge) ValidateOAuthCredentialUnlink(_ context.Context, accountID, credentialID string) error {
	if bridge.Identity == nil {
		return newOAuthPublicError(http.StatusServiceUnavailable, "identity_service_unavailable", "canonical identity service is unavailable", nil)
	}
	return oauthIdentityBridgeError(bridge.Identity.CanUnlinkCredential(accountID, credentialID))
}

func (bridge UnifiedIdentityOAuthBridge) UnlinkOAuthCredential(_ context.Context, accountID, credentialID, actorID string) error {
	if bridge.Identity == nil {
		return newOAuthPublicError(http.StatusServiceUnavailable, "identity_service_unavailable", "canonical identity service is unavailable", nil)
	}
	_, err := bridge.Identity.UnlinkCredential(accountID, credentialID, actorID)
	return oauthIdentityBridgeError(err)
}

func oauthIdentityProvider(provider string) (IdentityProvider, error) {
	switch strings.ToLower(strings.TrimSpace(provider)) {
	case "github":
		return IdentityProviderGitHub, nil
	case "google":
		return IdentityProviderGoogle, nil
	case "wechat":
		return IdentityProviderWeChat, nil
	case "qq":
		return IdentityProviderQQ, nil
	case "alipay":
		return IdentityProviderAlipay, nil
	default:
		return "", newOAuthPublicError(http.StatusBadRequest, "unsupported_oauth_provider", "OAuth provider is not supported by canonical identity", nil)
	}
}

func oauthIdentityBridgeError(err error) error {
	if err == nil {
		return nil
	}
	var oauthError OAuthError
	if errors.As(err, &oauthError) {
		return oauthError
	}
	var domainError IdentityDomainError
	if errors.As(err, &domainError) {
		switch domainError.Code {
		case "credential_link_conflict":
			return newOAuthPublicError(http.StatusConflict, domainError.Code, "credential is already linked to another account", err)
		case "last_login_credential":
			return newOAuthPublicError(http.StatusConflict, domainError.Code, "the final login-capable credential cannot be disconnected", err)
		default:
			return newOAuthPublicError(http.StatusBadRequest, domainError.Code, "canonical identity operation was rejected", err)
		}
	}
	if errors.Is(err, ErrIdentityAccountNotFound) || errors.Is(err, ErrIdentityCredentialNotFound) {
		return newOAuthPublicError(http.StatusNotFound, "identity_not_found", "canonical identity record was not found", err)
	}
	return newOAuthPublicError(http.StatusInternalServerError, "identity_operation_failed", "canonical identity operation failed", err)
}
