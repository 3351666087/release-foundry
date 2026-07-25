package ashrclone

import (
	"bytes"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"net"
	"net/http"
	"strings"
	"time"
)

const (
	maxIdentityDeliveryMTLSCABundleBytes    = 1024 * 1024
	maxIdentityDeliveryMTLSCertificateBytes = 256 * 1024
	maxIdentityDeliveryMTLSPrivateKeyBytes  = 256 * 1024
	maxIdentityDeliveryMTLSTimeout          = 2 * time.Minute
)

var errIdentityDeliveryMTLSConfiguration = errors.New(
	"identity delivery mTLS configuration is invalid",
)

// IdentityDeliveryMTLSClientOptions contains the complete trust and workload
// identity profile for one sidecar. System roots and ambient proxy settings are
// intentionally ignored.
type IdentityDeliveryMTLSClientOptions struct {
	CABundlePEM           []byte
	ClientCertificatePEM  []byte
	ClientPrivateKeyPEM   []byte
	ServerName            string
	MinimumTLSVersion     uint16
	MaximumTLSVersion     uint16
	DialTimeout           time.Duration
	TLSHandshakeTimeout   time.Duration
	ResponseHeaderTimeout time.Duration
	RequestTimeout        time.Duration
}

// NewIdentityDeliveryMTLSHTTPClient constructs a fail-closed client that trusts
// only the supplied CA bundle and always presents the supplied client identity.
func NewIdentityDeliveryMTLSHTTPClient(
	options IdentityDeliveryMTLSClientOptions,
) (*http.Client, error) {
	minimumTLSVersion, maximumTLSVersion, versionsOK :=
		identityDeliveryMTLSVersions(
			options.MinimumTLSVersion,
			options.MaximumTLSVersion,
		)
	if !validIdentityDeliveryMTLSTimeout(options.DialTimeout) ||
		!validIdentityDeliveryMTLSTimeout(options.TLSHandshakeTimeout) ||
		!validIdentityDeliveryMTLSTimeout(options.ResponseHeaderTimeout) ||
		!validIdentityDeliveryMTLSTimeout(options.RequestTimeout) ||
		options.DialTimeout > options.RequestTimeout ||
		options.TLSHandshakeTimeout > options.RequestTimeout ||
		options.ResponseHeaderTimeout > options.RequestTimeout ||
		!versionsOK ||
		!validIdentityDeliveryMTLSServerName(options.ServerName) {
		return nil, errIdentityDeliveryMTLSConfiguration
	}
	if len(options.CABundlePEM) == 0 ||
		len(options.CABundlePEM) > maxIdentityDeliveryMTLSCABundleBytes ||
		len(options.ClientCertificatePEM) == 0 ||
		len(options.ClientCertificatePEM) > maxIdentityDeliveryMTLSCertificateBytes ||
		len(options.ClientPrivateKeyPEM) == 0 ||
		len(options.ClientPrivateKeyPEM) > maxIdentityDeliveryMTLSPrivateKeyBytes {
		return nil, errIdentityDeliveryMTLSConfiguration
	}

	roots, err := identityDeliveryMTLSCertPool(options.CABundlePEM)
	if err != nil {
		return nil, errIdentityDeliveryMTLSConfiguration
	}
	certificate, err := tls.X509KeyPair(
		options.ClientCertificatePEM,
		options.ClientPrivateKeyPEM,
	)
	if err != nil || len(certificate.Certificate) == 0 {
		return nil, errIdentityDeliveryMTLSConfiguration
	}
	leaf, err := x509.ParseCertificate(certificate.Certificate[0])
	if err != nil {
		return nil, errIdentityDeliveryMTLSConfiguration
	}
	certificate.Leaf = leaf

	transport := &http.Transport{
		Proxy: nil,
		DialContext: (&net.Dialer{
			Timeout:   options.DialTimeout,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		ForceAttemptHTTP2:     true,
		MaxIdleConns:          32,
		MaxIdleConnsPerHost:   8,
		MaxConnsPerHost:       32,
		IdleConnTimeout:       30 * time.Second,
		TLSHandshakeTimeout:   options.TLSHandshakeTimeout,
		ResponseHeaderTimeout: options.ResponseHeaderTimeout,
		ExpectContinueTimeout: time.Second,
		DisableCompression:    true,
		TLSClientConfig: &tls.Config{
			MinVersion:   minimumTLSVersion,
			MaxVersion:   maximumTLSVersion,
			RootCAs:      roots,
			Certificates: []tls.Certificate{certificate},
			ServerName:   options.ServerName,
		},
	}
	return &http.Client{
		Transport: transport,
		Timeout:   options.RequestTimeout,
		CheckRedirect: func(*http.Request, []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}, nil
}

func identityDeliveryMTLSVersions(
	minimum uint16,
	maximum uint16,
) (uint16, uint16, bool) {
	if minimum == 0 {
		minimum = tls.VersionTLS12
	}
	if minimum != tls.VersionTLS12 && minimum != tls.VersionTLS13 {
		return 0, 0, false
	}
	if maximum != 0 &&
		maximum != tls.VersionTLS12 &&
		maximum != tls.VersionTLS13 {
		return 0, 0, false
	}
	if maximum != 0 && maximum < minimum {
		return 0, 0, false
	}
	return minimum, maximum, true
}

func identityDeliveryMTLSCertPool(encoded []byte) (*x509.CertPool, error) {
	roots := x509.NewCertPool()
	rest := bytes.TrimSpace(encoded)
	certificates := 0
	for len(rest) > 0 {
		if !bytes.HasPrefix(rest, []byte("-----BEGIN CERTIFICATE-----")) {
			return nil, errIdentityDeliveryMTLSConfiguration
		}
		block, trailing := pem.Decode(rest)
		if block == nil || block.Type != "CERTIFICATE" || len(block.Headers) != 0 {
			return nil, errIdentityDeliveryMTLSConfiguration
		}
		certificate, err := x509.ParseCertificate(block.Bytes)
		if err != nil {
			return nil, errIdentityDeliveryMTLSConfiguration
		}
		roots.AddCert(certificate)
		certificates++
		rest = bytes.TrimSpace(trailing)
	}
	if certificates == 0 {
		return nil, errIdentityDeliveryMTLSConfiguration
	}
	return roots, nil
}

func validIdentityDeliveryMTLSTimeout(value time.Duration) bool {
	return value >= time.Millisecond && value <= maxIdentityDeliveryMTLSTimeout
}

func validIdentityDeliveryMTLSServerName(value string) bool {
	if value == "" || value != strings.TrimSpace(value) || len(value) > 253 ||
		strings.ContainsAny(value, "\x00\r\n/:\\") {
		return false
	}
	if net.ParseIP(value) != nil {
		return true
	}
	for _, label := range strings.Split(value, ".") {
		if len(label) == 0 || len(label) > 63 ||
			!identityDeliveryMTLSServerNameEdge(label[0]) ||
			!identityDeliveryMTLSServerNameEdge(label[len(label)-1]) {
			return false
		}
		for index := 1; index < len(label)-1; index++ {
			character := label[index]
			if !identityDeliveryMTLSServerNameEdge(character) && character != '-' {
				return false
			}
		}
	}
	return true
}

func identityDeliveryMTLSServerNameEdge(character byte) bool {
	return character >= 'a' && character <= 'z' ||
		character >= 'A' && character <= 'Z' ||
		character >= '0' && character <= '9'
}
