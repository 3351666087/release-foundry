package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestIdentitySecurityProcessorCommandConfigRejectsRawTokenAndPartialConfig(
	t *testing.T,
) {
	env := identitySecurityProcessorTestEnvironment(t)
	config, err := identitySecurityProcessorCommandConfigFromEnv(
		func(name string) (string, bool) {
			value, ok := env[name]
			return value, ok
		},
	)
	if err != nil {
		t.Fatalf("valid processor config rejected: %v", err)
	}
	if err := config.validate(); err != nil {
		t.Fatalf("valid processor config did not validate: %v", err)
	}
	env["ASHR_IDENTITY_SECURITY_VAULT_TOKEN"] = "hvs-raw-token-forbidden"
	if _, err := identitySecurityProcessorCommandConfigFromEnv(
		func(name string) (string, bool) {
			value, ok := env[name]
			return value, ok
		},
	); err == nil {
		t.Fatal("raw Vault token environment variable was accepted")
	}
	delete(env, "ASHR_IDENTITY_SECURITY_VAULT_TOKEN")
	delete(env, "ASHR_IDENTITY_SECURITY_VAULT_TOKEN_FILE")
	if _, err := identitySecurityProcessorCommandConfigFromEnv(
		func(name string) (string, bool) {
			value, ok := env[name]
			return value, ok
		},
	); err == nil {
		t.Fatal("partial Vault token configuration was accepted")
	}
}

func TestIdentitySecurityProcessorTLSRequiresClientCertificateAndTLS13(
	t *testing.T,
) {
	caCertPEM, caKey, caCert := identitySecurityProcessorTestCA(t)
	serverCertPEM, serverKeyPEM := identitySecurityProcessorTestLeaf(
		t,
		caCert,
		caKey,
		"processor.test",
		[]x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	)
	clientCertPEM, clientKeyPEM := identitySecurityProcessorTestLeaf(
		t,
		caCert,
		caKey,
		"operator.test",
		[]x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	)
	dir := t.TempDir()
	config := identitySecurityProcessorCommandConfig{
		serverCertificateFile: writeIdentitySecurityProcessorTestFile(
			t, dir, "server.crt", serverCertPEM,
		),
		serverPrivateKeyFile: writeIdentitySecurityProcessorTestFile(
			t, dir, "server.key", serverKeyPEM,
		),
		clientCAFile: writeIdentitySecurityProcessorTestFile(
			t, dir, "client-ca.crt", caCertPEM,
		),
	}
	tlsConfig, err := newIdentitySecurityProcessorServerTLSConfig(config)
	if err != nil {
		t.Fatalf("new processor server TLS config: %v", err)
	}
	if tlsConfig.MinVersion != tls.VersionTLS13 ||
		tlsConfig.MaxVersion != tls.VersionTLS13 ||
		tlsConfig.ClientAuth != tls.RequireAndVerifyClientCert {
		t.Fatalf("processor TLS posture is not TLS 1.3 mTLS")
	}
	listener, err := tls.Listen("tcp", "127.0.0.1:0", tlsConfig)
	if err != nil {
		t.Fatalf("listen processor TLS: %v", err)
	}
	server := &http.Server{
		Handler: http.HandlerFunc(func(
			writer http.ResponseWriter,
			request *http.Request,
		) {
			writer.WriteHeader(http.StatusNoContent)
		}),
	}
	serverDone := make(chan error, 1)
	go func() { serverDone <- server.Serve(listener) }()
	defer func() {
		_ = server.Close()
		<-serverDone
	}()

	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caCertPEM) {
		t.Fatal("append test CA")
	}
	noClient := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				MinVersion: tls.VersionTLS13,
				MaxVersion: tls.VersionTLS13,
				RootCAs:    roots,
				ServerName: "processor.test",
			},
		},
		Timeout: time.Second,
	}
	if _, err := noClient.Get("https://" + listener.Addr().String()); err == nil {
		t.Fatal("processor TLS server accepted a client without a certificate")
	}
	clientCert, err := tls.X509KeyPair(clientCertPEM, clientKeyPEM)
	if err != nil {
		t.Fatal(err)
	}
	withClient := &http.Client{
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{
				MinVersion:   tls.VersionTLS13,
				MaxVersion:   tls.VersionTLS13,
				RootCAs:      roots,
				ServerName:   "processor.test",
				Certificates: []tls.Certificate{clientCert},
			},
		},
		Timeout: time.Second,
	}
	response, err := withClient.Get("https://" + listener.Addr().String())
	if err != nil {
		t.Fatalf("mTLS processor request failed: %v", err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("mTLS processor status=%d", response.StatusCode)
	}
}

func TestIdentitySecurityProcessorVaultHTTPClientUsesTLS13ClientCertificate(
	t *testing.T,
) {
	caCertPEM, caKey, caCert := identitySecurityProcessorTestCA(t)
	serverCertPEM, serverKeyPEM := identitySecurityProcessorTestLeaf(
		t,
		caCert,
		caKey,
		"vault.test",
		[]x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	)
	clientCertPEM, clientKeyPEM := identitySecurityProcessorTestLeaf(
		t,
		caCert,
		caKey,
		"processor.test",
		[]x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth},
	)
	dir := t.TempDir()
	config := identitySecurityProcessorCommandConfig{
		vaultCAFile: writeIdentitySecurityProcessorTestFile(
			t, dir, "vault-ca.crt", caCertPEM,
		),
		vaultClientCertificateFile: writeIdentitySecurityProcessorTestFile(
			t, dir, "vault-client.crt", clientCertPEM,
		),
		vaultClientPrivateKeyFile: writeIdentitySecurityProcessorTestFile(
			t, dir, "vault-client.key", clientKeyPEM,
		),
		vaultServerName: "vault.test",
		vaultTimeout:    time.Second,
	}
	tlsConfig := &tls.Config{
		MinVersion: tls.VersionTLS13,
		MaxVersion: tls.VersionTLS13,
		Certificates: mustIdentitySecurityProcessorTestTLSCertificate(
			t,
			serverCertPEM,
			serverKeyPEM,
		),
		ClientAuth: tls.RequireAndVerifyClientCert,
		ClientCAs:  mustIdentitySecurityProcessorTestCAPool(t, caCertPEM),
	}
	listener, err := tls.Listen("tcp", "127.0.0.1:0", tlsConfig)
	if err != nil {
		t.Fatal(err)
	}
	server := &http.Server{
		Handler: http.HandlerFunc(func(
			writer http.ResponseWriter,
			request *http.Request,
		) {
			if request.TLS == nil || len(request.TLS.PeerCertificates) != 1 {
				t.Error("Vault test server did not receive a client certificate")
			}
			writer.WriteHeader(http.StatusNoContent)
		}),
	}
	serverDone := make(chan error, 1)
	go func() { serverDone <- server.Serve(listener) }()
	defer func() {
		_ = server.Close()
		<-serverDone
	}()
	client, err := newIdentitySecurityProcessorVaultHTTPClient(config)
	if err != nil {
		t.Fatalf("new Vault mTLS client: %v", err)
	}
	defer client.CloseIdleConnections()
	response, err := client.Get("https://" + listener.Addr().String())
	if err != nil {
		t.Fatalf("Vault mTLS client request failed: %v", err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("Vault mTLS client status=%d", response.StatusCode)
	}
	transport := client.Transport.(*http.Transport)
	if transport.TLSClientConfig.MinVersion != tls.VersionTLS13 ||
		transport.TLSClientConfig.MaxVersion != tls.VersionTLS13 ||
		len(transport.TLSClientConfig.Certificates) != 1 {
		t.Fatalf("Vault client TLS posture is not TLS 1.3 mTLS")
	}
}

func TestIdentitySecurityProcessorBoundedTLSFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), "oversized")
	if err := os.WriteFile(
		path,
		[]byte(strings.Repeat("x", maxIdentitySecurityProcessorTLSFileBytes+1)),
		0o600,
	); err != nil {
		t.Fatal(err)
	}
	if _, err := readIdentitySecurityProcessorBoundedFile(
		path,
		maxIdentitySecurityProcessorTLSFileBytes,
	); err == nil {
		t.Fatal("oversized TLS file was accepted")
	}
}

func identitySecurityProcessorTestEnvironment(t *testing.T) map[string]string {
	t.Helper()
	dir := t.TempDir()
	return map[string]string{
		"ASHR_IDENTITY_SECURITY_PROCESSOR_LISTEN_ADDRESS":       "127.0.0.1:8443",
		"ASHR_IDENTITY_SECURITY_PROCESSOR_SERVER_CERT_FILE":     filepath.Join(dir, "server.crt"),
		"ASHR_IDENTITY_SECURITY_PROCESSOR_SERVER_KEY_FILE":      filepath.Join(dir, "server.key"),
		"ASHR_IDENTITY_SECURITY_PROCESSOR_CLIENT_CA_FILE":       filepath.Join(dir, "client-ca.crt"),
		"ASHR_IDENTITY_SECURITY_VAULT_DATA_ENDPOINT_PREFIX":     "https://vault.test/v1/secret/data/ashr/identity-security/records",
		"ASHR_IDENTITY_SECURITY_VAULT_METADATA_ENDPOINT_PREFIX": "https://vault.test/v1/secret/metadata/ashr/identity-security/records",
		"ASHR_IDENTITY_SECURITY_VAULT_KEYRING_ENDPOINT":         "https://vault.test/v1/secret/data/ashr/identity-security/keyring",
		"ASHR_IDENTITY_SECURITY_VAULT_TOKEN_FILE":               filepath.Join(dir, "vault-token"),
		"ASHR_IDENTITY_SECURITY_VAULT_CA_FILE":                  filepath.Join(dir, "vault-ca.crt"),
		"ASHR_IDENTITY_SECURITY_VAULT_CLIENT_CERT_FILE":         filepath.Join(dir, "vault-client.crt"),
		"ASHR_IDENTITY_SECURITY_VAULT_CLIENT_KEY_FILE":          filepath.Join(dir, "vault-client.key"),
		"ASHR_IDENTITY_SECURITY_VAULT_SERVER_NAME":              "vault.test",
	}
}

func identitySecurityProcessorTestCA(
	t *testing.T,
) ([]byte, *ecdsa.PrivateKey, *x509.Certificate) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "Ashr test CA"},
		NotBefore:             time.Now().Add(-time.Minute),
		NotAfter:              time.Now().Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageCRLSign,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatal(err)
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatal(err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		key,
		certificate
}

func identitySecurityProcessorTestLeaf(
	t *testing.T,
	ca *x509.Certificate,
	caKey *ecdsa.PrivateKey,
	commonName string,
	usages []x509.ExtKeyUsage,
) ([]byte, []byte) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(time.Now().UnixNano()),
		Subject:      pkix.Name{CommonName: commonName},
		DNSNames:     []string{commonName},
		NotBefore:    time.Now().Add(-time.Minute),
		NotAfter:     time.Now().Add(time.Hour),
		ExtKeyUsage:  usages,
		KeyUsage:     x509.KeyUsageDigitalSignature,
	}
	der, err := x509.CreateCertificate(
		rand.Reader,
		template,
		ca,
		&key.PublicKey,
		caKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	keyBytes, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatal(err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyBytes})
}

func mustIdentitySecurityProcessorTestTLSCertificate(
	t *testing.T,
	certificatePEM []byte,
	keyPEM []byte,
) []tls.Certificate {
	t.Helper()
	certificate, err := tls.X509KeyPair(certificatePEM, keyPEM)
	if err != nil {
		t.Fatal(err)
	}
	return []tls.Certificate{certificate}
}

func mustIdentitySecurityProcessorTestCAPool(
	t *testing.T,
	certificatePEM []byte,
) *x509.CertPool {
	t.Helper()
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(certificatePEM) {
		t.Fatal("append test CA")
	}
	return roots
}

func writeIdentitySecurityProcessorTestFile(
	t *testing.T,
	dir string,
	name string,
	payload []byte,
) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, payload, 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}
