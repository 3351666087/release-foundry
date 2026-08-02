package main

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"net/mail"
	"net/smtp"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/3351666087/release-foundry/packages/go/releasefoundry"
)

type localIdentityDeliveryMailSealer struct {
	host       string
	address    string
	from       string
	consoleURL string
	timeout    time.Duration
}

func newLocalIdentityDeliveryMailSealer(
	lookup func(string) (string, bool),
) (*localIdentityDeliveryMailSealer, error) {
	host := env(lookup, "RELEASEFOUNDRY_IDENTITY_LOCAL_MAIL_HOST")
	portValue := env(lookup, "RELEASEFOUNDRY_IDENTITY_LOCAL_MAIL_PORT")
	from := env(lookup, "RELEASEFOUNDRY_IDENTITY_LOCAL_MAIL_FROM")
	consoleURL := env(lookup, "RELEASEFOUNDRY_IDENTITY_LOCAL_MAIL_CONSOLE_URL")
	port, err := strconv.Atoi(portValue)
	parsedFrom, fromErr := mail.ParseAddress(from)
	parsedConsole, consoleErr := url.Parse(consoleURL)
	if host == "" || strings.ContainsAny(host, "\x00\r\n") ||
		err != nil || port < 1 || port > 65535 ||
		fromErr != nil || parsedFrom.Address != from ||
		consoleErr != nil || parsedConsole.Scheme != "http" ||
		parsedConsole.Host == "" || parsedConsole.User != nil {
		return nil, fmt.Errorf("local identity mail delivery configuration is invalid")
	}
	return &localIdentityDeliveryMailSealer{
		host: host, address: net.JoinHostPort(host, strconv.Itoa(port)),
		from: from, consoleURL: parsedConsole.String(), timeout: 5 * time.Second,
	}, nil
}

func (sealer *localIdentityDeliveryMailSealer) SealIdentityDelivery(
	ctx context.Context,
	request releasefoundry.IdentityDeliverySealRequest,
) (string, error) {
	if sealer == nil || ctx == nil || request.Channel != releasefoundry.IdentityVerificationEmail ||
		len(request.Code) != 6 || request.ReservationID == "" ||
		request.ChallengeHandle == "" || !request.ExpiresAt.After(time.Now()) {
		return "", fmt.Errorf("local identity mail delivery request is invalid")
	}
	for _, character := range request.Code {
		if character < '0' || character > '9' {
			return "", fmt.Errorf("local identity mail delivery request is invalid")
		}
	}
	destination, err := mail.ParseAddress(request.Destination)
	if err != nil || destination.Address != request.Destination ||
		strings.ContainsAny(request.Destination, "\r\n") {
		return "", fmt.Errorf("local identity mail delivery request is invalid")
	}
	dialer := net.Dialer{Timeout: sealer.timeout}
	connection, err := dialer.DialContext(ctx, "tcp", sealer.address)
	if err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	defer connection.Close()
	client, err := smtp.NewClient(connection, sealer.host)
	if err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	defer client.Close()
	if err := client.Mail(sealer.from); err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	if err := client.Rcpt(destination.Address); err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	writer, err := client.Data()
	if err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	if _, err := io.WriteString(writer, sealer.message(request)); err != nil {
		_ = writer.Close()
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	if err := writer.Close(); err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	if err := client.Quit(); err != nil {
		return "", fmt.Errorf("local identity mail delivery is unavailable")
	}
	return "opaque-ref:local-mail/" + request.ReservationID, nil
}

func (sealer *localIdentityDeliveryMailSealer) DeleteIdentityDelivery(
	context.Context,
	string,
) error {
	return nil
}

func (sealer *localIdentityDeliveryMailSealer) message(
	request releasefoundry.IdentityDeliverySealRequest,
) string {
	var body strings.Builder
	writer := bufio.NewWriter(&body)
	_, _ = fmt.Fprintf(writer, "From: %s\r\n", sealer.from)
	_, _ = fmt.Fprintf(writer, "To: %s\r\n", request.Destination)
	_, _ = fmt.Fprint(writer, "Subject: ReleaseFoundry local verification code\r\n")
	_, _ = fmt.Fprint(writer, "MIME-Version: 1.0\r\n")
	_, _ = fmt.Fprint(writer, "Content-Type: text/plain; charset=UTF-8\r\n\r\n")
	_, _ = fmt.Fprintln(writer, "ReleaseFoundry local development identity verification")
	_, _ = fmt.Fprintln(writer)
	_, _ = fmt.Fprintf(writer, "Verification code: %s\r\n", request.Code)
	_, _ = fmt.Fprintf(writer, "Purpose: %s\r\n", request.Purpose)
	_, _ = fmt.Fprintf(writer, "Expires at: %s\r\n", request.ExpiresAt.UTC().Format(time.RFC3339))
	_, _ = fmt.Fprintf(writer, "Local inbox: %s\r\n", sealer.consoleURL)
	_, _ = fmt.Fprintln(writer, "This local-only message does not use a production SMTP provider.")
	_ = writer.Flush()
	return body.String()
}

var (
	_ releasefoundry.IdentityDeliveryVaultSealer  = (*localIdentityDeliveryMailSealer)(nil)
	_ releasefoundry.IdentityDeliveryVaultDeleter = (*localIdentityDeliveryMailSealer)(nil)
)
