package releasefoundry

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

type identityDeliveryMTLSTestAuthority struct {
	certificate    *x509.Certificate
	privateKey     *ecdsa.PrivateKey
	certificatePEM []byte
}

func TestIdentityDeliveryMTLSClientRequiresAndAuthenticatesBothPeers(t *testing.T) {
	authority := newIdentityDeliveryMTLSTestAuthority(t, "identity-delivery-ca")
	serverCertificate, serverKey := authority.issueIdentityDeliveryMTLSCertificate(
		t, "identity-delivery-sidecar", false,
	)
	clientCertificate, clientKey := authority.issueIdentityDeliveryMTLSCertificate(
		t, "identity-delivery-worker", true,
	)
	serverPair, err := tls.X509KeyPair(serverCertificate, serverKey)
	if err != nil {
		t.Fatal(err)
	}
	clientRoots := x509.NewCertPool()
	clientRoots.AddCert(authority.certificate)
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.TLS == nil || len(request.TLS.PeerCertificates) == 0 {
			t.Error("authenticated request had no client certificate")
		}
		writer.WriteHeader(http.StatusNoContent)
	}))
	server.Config.ErrorLog = log.New(io.Discard, "", 0)
	server.TLS = &tls.Config{
		MinVersion:   tls.VersionTLS12,
		Certificates: []tls.Certificate{serverPair},
		ClientAuth:   tls.RequireAndVerifyClientCert,
		ClientCAs:    clientRoots,
	}
	server.StartTLS()
	defer server.Close()

	noClientTransport := &http.Transport{TLSClientConfig: &tls.Config{
		MinVersion: tls.VersionTLS12,
		RootCAs:    clientRoots,
		ServerName: "127.0.0.1",
	}}
	noClient := &http.Client{Transport: noClientTransport, Timeout: time.Second}
	if response, requestErr := noClient.Get(server.URL); requestErr == nil {
		response.Body.Close()
		t.Fatal("server accepted a request without a client certificate")
	}
	noClient.CloseIdleConnections()

	wrongAuthority := newIdentityDeliveryMTLSTestAuthority(t, "wrong-ca")
	wrongCAClient := newIdentityDeliveryMTLSTestClient(
		t, wrongAuthority.certificatePEM, clientCertificate, clientKey,
	)
	if response, requestErr := wrongCAClient.Get(server.URL); requestErr == nil {
		response.Body.Close()
		t.Fatal("client accepted a server from an untrusted CA")
	}
	wrongCAClient.CloseIdleConnections()

	client := newIdentityDeliveryMTLSTestClient(
		t, authority.certificatePEM, clientCertificate, clientKey,
	)
	defer client.CloseIdleConnections()
	response, err := client.Get(server.URL)
	if err != nil {
		t.Fatal(err)
	}
	response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("authenticated status = %d", response.StatusCode)
	}
}

func TestIdentityDeliveryMTLSClientRefusesSecretBearingRedirect(t *testing.T) {
	authority := newIdentityDeliveryMTLSTestAuthority(t, "redirect-ca")
	serverCertificate, serverKey := authority.issueIdentityDeliveryMTLSCertificate(
		t, "redirect-sidecar", false,
	)
	clientCertificate, clientKey := authority.issueIdentityDeliveryMTLSCertificate(
		t, "redirect-worker", true,
	)
	serverPair, err := tls.X509KeyPair(serverCertificate, serverKey)
	if err != nil {
		t.Fatal(err)
	}
	clientRoots := x509.NewCertPool()
	clientRoots.AddCert(authority.certificate)
	var targetCalls atomic.Int32
	target := newIdentityDeliveryMTLSTestServer(t, serverPair, clientRoots, http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		targetCalls.Add(1)
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer target.Close()
	redirect := newIdentityDeliveryMTLSTestServer(t, serverPair, clientRoots, http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		http.Redirect(writer, request, target.URL+"/consume", http.StatusTemporaryRedirect)
	}))
	defer redirect.Close()
	client := newIdentityDeliveryMTLSTestClient(
		t, authority.certificatePEM, clientCertificate, clientKey,
	)
	defer client.CloseIdleConnections()
	secret := "verification-code-that-must-not-be-replayed"
	response, err := client.Post(
		redirect.URL,
		"application/json",
		strings.NewReader(`{"code":"`+secret+`"}`),
	)
	if err != nil {
		if strings.Contains(err.Error(), secret) {
			t.Fatalf("redirect error exposed secret: %q", err)
		}
		t.Fatal(err)
	}
	defer response.Body.Close()
	_, _ = io.Copy(io.Discard, response.Body)
	if response.StatusCode != http.StatusTemporaryRedirect || targetCalls.Load() != 0 {
		t.Fatalf("redirect was followed: status=%d target_calls=%d", response.StatusCode, targetCalls.Load())
	}
}

func TestIdentityDeliveryMTLSClientRejectsInvalidSecretMaterialSafely(t *testing.T) {
	secret := "private-key-material-that-must-not-leak"
	_, err := NewIdentityDeliveryMTLSHTTPClient(IdentityDeliveryMTLSClientOptions{
		CABundlePEM:           []byte("not-a-ca"),
		ClientCertificatePEM:  []byte("not-a-certificate"),
		ClientPrivateKeyPEM:   []byte(secret),
		ServerName:            "sidecar.internal",
		DialTimeout:           time.Second,
		TLSHandshakeTimeout:   time.Second,
		ResponseHeaderTimeout: time.Second,
		RequestTimeout:        time.Second,
	})
	if err == nil || err.Error() != "identity delivery mTLS configuration is invalid" {
		t.Fatalf("unexpected configuration error: %v", err)
	}
	if strings.Contains(err.Error(), secret) {
		t.Fatalf("configuration error exposed key material: %q", err)
	}
}

func newIdentityDeliveryMTLSTestClient(
	t *testing.T,
	caPEM []byte,
	certificatePEM []byte,
	privateKeyPEM []byte,
) *http.Client {
	t.Helper()
	client, err := NewIdentityDeliveryMTLSHTTPClient(IdentityDeliveryMTLSClientOptions{
		CABundlePEM:           caPEM,
		ClientCertificatePEM:  certificatePEM,
		ClientPrivateKeyPEM:   privateKeyPEM,
		ServerName:            "127.0.0.1",
		DialTimeout:           time.Second,
		TLSHandshakeTimeout:   time.Second,
		ResponseHeaderTimeout: time.Second,
		RequestTimeout:        2 * time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	return client
}

func newIdentityDeliveryMTLSTestServer(
	t *testing.T,
	certificate tls.Certificate,
	clientRoots *x509.CertPool,
	handler http.Handler,
) *httptest.Server {
	t.Helper()
	server := httptest.NewUnstartedServer(handler)
	server.Config.ErrorLog = log.New(io.Discard, "", 0)
	server.TLS = &tls.Config{
		MinVersion:   tls.VersionTLS12,
		Certificates: []tls.Certificate{certificate},
		ClientAuth:   tls.RequireAndVerifyClientCert,
		ClientCAs:    clientRoots,
	}
	server.StartTLS()
	return server
}

func newIdentityDeliveryMTLSTestAuthority(
	t *testing.T,
	commonName string,
) identityDeliveryMTLSTestAuthority {
	t.Helper()
	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(now.UnixNano()),
		Subject:               pkix.Name{CommonName: commonName},
		NotBefore:             now.Add(-time.Minute),
		NotAfter:              now.Add(time.Hour),
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
		BasicConstraintsValid: true,
		IsCA:                  true,
	}
	encoded, err := x509.CreateCertificate(
		rand.Reader, template, template, &privateKey.PublicKey, privateKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	certificate, err := x509.ParseCertificate(encoded)
	if err != nil {
		t.Fatal(err)
	}
	return identityDeliveryMTLSTestAuthority{
		certificate: certificate,
		privateKey:  privateKey,
		certificatePEM: pem.EncodeToMemory(&pem.Block{
			Type: "CERTIFICATE", Bytes: encoded,
		}),
	}
}

func (authority identityDeliveryMTLSTestAuthority) issueIdentityDeliveryMTLSCertificate(
	t *testing.T,
	commonName string,
	client bool,
) ([]byte, []byte) {
	t.Helper()
	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	usage := x509.ExtKeyUsageServerAuth
	if client {
		usage = x509.ExtKeyUsageClientAuth
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(now.UnixNano()),
		Subject:      pkix.Name{CommonName: commonName},
		NotBefore:    now.Add(-time.Minute),
		NotAfter:     now.Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{usage},
	}
	if !client {
		template.IPAddresses = []net.IP{net.ParseIP("127.0.0.1")}
	}
	encodedCertificate, err := x509.CreateCertificate(
		rand.Reader,
		template,
		authority.certificate,
		&privateKey.PublicKey,
		authority.privateKey,
	)
	if err != nil {
		t.Fatal(err)
	}
	encodedPrivateKey, err := x509.MarshalPKCS8PrivateKey(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	return pem.EncodeToMemory(&pem.Block{
			Type: "CERTIFICATE", Bytes: encodedCertificate,
		}), pem.EncodeToMemory(&pem.Block{
			Type: "PRIVATE KEY", Bytes: encodedPrivateKey,
		})
}

func TestIdentityDeliveryMTLSClientDoesNotRetainInputSlices(t *testing.T) {
	authority := newIdentityDeliveryMTLSTestAuthority(t, "copy-ca")
	certificate, key := authority.issueIdentityDeliveryMTLSCertificate(t, "copy-client", true)
	ca := bytes.Clone(authority.certificatePEM)
	client, err := NewIdentityDeliveryMTLSHTTPClient(IdentityDeliveryMTLSClientOptions{
		CABundlePEM: ca, ClientCertificatePEM: certificate, ClientPrivateKeyPEM: key,
		ServerName: "sidecar.internal", DialTimeout: time.Second,
		TLSHandshakeTimeout: time.Second, ResponseHeaderTimeout: time.Second,
		RequestTimeout: time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer client.CloseIdleConnections()
	clear(ca)
	clear(certificate)
	clear(key)
	transport := client.Transport.(*http.Transport)
	if transport.TLSClientConfig.RootCAs == nil ||
		len(transport.TLSClientConfig.Certificates) != 1 {
		t.Fatal("clearing source PEM removed parsed trust or identity")
	}
}
