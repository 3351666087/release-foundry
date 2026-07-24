package ashrclone

import (
	"net/url"
	"strings"
	"testing"
)

func TestBuildIdentityVerificationBrowserURLUsesOpaqueMailboxContext(t *testing.T) {
	challengeID := "ivc_444444444444444444444444444444444444"
	result, err := BuildIdentityVerificationBrowserURL(
		"https://app.example.test/login/verify",
		challengeID,
		IdentityVerificationLogin,
	)
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := url.Parse(result)
	if err != nil {
		t.Fatal(err)
	}
	if parsed.Scheme != "https" || parsed.Host != "app.example.test" ||
		parsed.Path != "/login/verify" ||
		parsed.Query().Get(IdentityVerificationChallengeQueryParameter) != challengeID ||
		parsed.Query().Get(IdentityVerificationPurposeQueryParameter) != "login" ||
		len(parsed.Query()) != 2 {
		t.Fatalf("unexpected verification URL: %q", result)
	}
	for _, forbidden := range []string{"person@example.test", "314159", "identifier", "code"} {
		if strings.Contains(result, forbidden) {
			t.Fatalf("verification URL exposed %q: %q", forbidden, result)
		}
	}
}

func TestBuildIdentityVerificationBrowserURLRejectsUnsafeConfiguration(t *testing.T) {
	challengeID := "ivc_444444444444444444444444444444444444"
	for _, raw := range []string{
		"http://app.example.test/login/verify",
		"https://user@app.example.test/login/verify",
		"https://app.example.test/login/verify#fragment",
		"https://app.example.test/login/verify?next=/console",
		"https://app.example.test/login/../admin",
		"https://app.example.test/login%2Fverify",
		"https://app.example.test\\@attacker.test/login/verify",
		"https://app.example.test/login/verify\r\nX-Unsafe: yes",
		" https://app.example.test/login/verify",
	} {
		if _, err := BuildIdentityVerificationBrowserURL(
			raw, challengeID, IdentityVerificationBinding,
		); err == nil {
			t.Fatalf("unsafe browser URL was accepted: %q", raw)
		}
	}
}

func TestBuildIdentityVerificationBrowserURLRejectsUnsafeContext(t *testing.T) {
	for _, test := range []struct {
		challengeID string
		purpose     IdentityVerificationPurpose
	}{
		{challengeID: "challenge-visible", purpose: IdentityVerificationLogin},
		{challengeID: "ivc_444444444444444444444444444444444444\r\nX: y", purpose: IdentityVerificationLogin},
		{challengeID: "ivc_444444444444444444444444444444444444", purpose: "signup"},
	} {
		if _, err := BuildIdentityVerificationBrowserURL(
			"https://app.example.test/login/verify",
			test.challengeID,
			test.purpose,
		); err == nil {
			t.Fatalf("unsafe browser context was accepted: %#v", test)
		}
	}
}
