package ashrclone

import (
	"bufio"
	"context"
	"crypto/tls"
	"fmt"
	"io"
	"net"
	"net/mail"
	"net/smtp"
	"strconv"
	"strings"
	"time"
)

const defaultSMTPIdentityVerificationTimeout = 10 * time.Second

type SMTPIdentityVerificationDialFunc func(context.Context, string, *tls.Config) (net.Conn, error)

type SMTPIdentityVerificationSenderOptions struct {
	Host                   string
	Port                   int
	ServerName             string
	From                   string
	AuthCode               string
	BrowserVerificationURL string
	Timeout                time.Duration
	DialTLS                SMTPIdentityVerificationDialFunc
}

type SMTPIdentityVerificationSender struct {
	host                   string
	address                string
	serverName             string
	from                   string
	authCode               string
	browserVerificationURL string
	timeout                time.Duration
	dialTLS                SMTPIdentityVerificationDialFunc
}

func NewSMTPIdentityVerificationSender(
	options SMTPIdentityVerificationSenderOptions,
) (*SMTPIdentityVerificationSender, error) {
	host := strings.TrimSpace(options.Host)
	serverName := strings.TrimSpace(options.ServerName)
	if serverName == "" {
		serverName = host
	}
	from, err := canonicalSMTPMailbox(options.From)
	if host == "" || containsSMTPHeaderBreak(host) {
		return nil, fmt.Errorf("SMTP host is invalid")
	}
	if options.Port < 1 || options.Port > 65535 {
		return nil, fmt.Errorf("SMTP port is invalid")
	}
	if serverName == "" || containsSMTPHeaderBreak(serverName) {
		return nil, fmt.Errorf("SMTP server name is invalid")
	}
	if err != nil {
		return nil, fmt.Errorf("SMTP sender mailbox is invalid")
	}
	if options.AuthCode == "" || containsSMTPHeaderBreak(options.AuthCode) {
		return nil, fmt.Errorf("SMTP authorization is invalid")
	}
	browserVerificationURL := strings.TrimSpace(options.BrowserVerificationURL)
	if browserVerificationURL != "" {
		if _, err := BuildIdentityVerificationBrowserURL(
			browserVerificationURL,
			"ivc_000000000000000000000000000000000000",
			IdentityVerificationBinding,
		); err != nil {
			return nil, fmt.Errorf("SMTP browser verification URL is invalid")
		}
	}
	timeout := options.Timeout
	if timeout <= 0 {
		timeout = defaultSMTPIdentityVerificationTimeout
	}
	dialTLS := options.DialTLS
	if dialTLS == nil {
		dialTLS = func(ctx context.Context, address string, config *tls.Config) (net.Conn, error) {
			dialer := &tls.Dialer{
				NetDialer: &net.Dialer{Timeout: timeout},
				Config:    config,
			}
			return dialer.DialContext(ctx, "tcp", address)
		}
	}
	return &SMTPIdentityVerificationSender{
		host: host, address: net.JoinHostPort(host, strconv.Itoa(options.Port)),
		serverName: serverName, from: from, authCode: options.AuthCode,
		browserVerificationURL: browserVerificationURL,
		timeout:                timeout, dialTLS: dialTLS,
	}, nil
}

func (sender *SMTPIdentityVerificationSender) SendIdentityVerification(
	ctx context.Context,
	delivery IdentityVerificationDelivery,
) error {
	if delivery.Channel != IdentityVerificationEmail {
		return fmt.Errorf("SMTP identity verification supports email delivery only")
	}
	destination, err := canonicalSMTPMailbox(delivery.Destination)
	if err != nil {
		return fmt.Errorf("SMTP identity verification destination is invalid")
	}
	if !validIdentityVerificationCode(delivery.Code) {
		return fmt.Errorf("SMTP identity verification code is invalid")
	}
	verificationURL := ""
	if sender.browserVerificationURL != "" {
		verificationURL, err = BuildIdentityVerificationBrowserURL(
			sender.browserVerificationURL,
			delivery.ChallengeID,
			delivery.Purpose,
		)
		if err != nil {
			return fmt.Errorf("SMTP identity verification browser context is invalid")
		}
	}

	sendCtx, cancel := context.WithTimeout(ctx, sender.timeout)
	defer cancel()
	conn, err := sender.dialTLS(sendCtx, sender.address, &tls.Config{
		MinVersion: tls.VersionTLS12,
		ServerName: sender.serverName,
	})
	if err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at connection")
	}
	defer conn.Close()
	if deadline, ok := sendCtx.Deadline(); ok {
		_ = conn.SetDeadline(deadline)
	}

	client, err := smtp.NewClient(conn, sender.host)
	if err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at greeting")
	}
	defer client.Close()
	if err := client.Auth(smtp.PlainAuth("", sender.from, sender.authCode, sender.host)); err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at authentication")
	}
	if err := client.Mail(sender.from); err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at sender")
	}
	if err := client.Rcpt(destination); err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at recipient")
	}
	writer, err := client.Data()
	if err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at message")
	}
	if _, err := io.WriteString(
		writer,
		identityVerificationEmail(sender.from, destination, verificationURL, delivery),
	); err != nil {
		_ = writer.Close()
		return fmt.Errorf("SMTP identity verification delivery failed at message")
	}
	if err := writer.Close(); err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at message")
	}
	if err := client.Quit(); err != nil {
		return fmt.Errorf("SMTP identity verification delivery failed at completion")
	}
	return nil
}

func canonicalSMTPMailbox(value string) (string, error) {
	value = strings.TrimSpace(value)
	if value == "" || containsSMTPHeaderBreak(value) {
		return "", fmt.Errorf("mailbox is invalid")
	}
	address, err := mail.ParseAddress(value)
	if err != nil || address.Address != value || containsSMTPHeaderBreak(address.Address) {
		return "", fmt.Errorf("mailbox is invalid")
	}
	return address.Address, nil
}

func containsSMTPHeaderBreak(value string) bool {
	return strings.ContainsAny(value, "\r\n")
}

func validIdentityVerificationCode(value string) bool {
	if len(value) != 6 {
		return false
	}
	for _, character := range value {
		if character < '0' || character > '9' {
			return false
		}
	}
	return true
}

func identityVerificationEmail(
	from string,
	destination string,
	verificationURL string,
	delivery IdentityVerificationDelivery,
) string {
	expiresAt := delivery.ExpiresAt.UTC().Format(time.RFC3339)
	var body strings.Builder
	writer := bufio.NewWriter(&body)
	_, _ = fmt.Fprintf(writer, "From: %s\r\n", from)
	_, _ = fmt.Fprintf(writer, "To: %s\r\n", destination)
	_, _ = fmt.Fprint(writer, "Subject: Ashr verification code\r\n")
	_, _ = fmt.Fprint(writer, "MIME-Version: 1.0\r\n")
	_, _ = fmt.Fprint(writer, "Content-Type: text/plain; charset=UTF-8\r\n")
	_, _ = fmt.Fprint(writer, "\r\n")
	_, _ = fmt.Fprint(writer, "Ashr 邮箱验证码 / Ashr email verification code\r\n\r\n")
	_, _ = fmt.Fprintf(writer, "Your Ashr verification code is: %s\r\n\r\n", delivery.Code)
	if verificationURL != "" {
		_, _ = fmt.Fprint(writer, "请使用以下安全链接继续验证 / Continue verification using this secure link:\r\n")
		_, _ = fmt.Fprintf(writer, "%s\r\n\r\n", verificationURL)
	}
	_, _ = fmt.Fprintf(writer, "This code expires at %s.\r\n", expiresAt)
	_, _ = fmt.Fprint(writer, "If you did not request this code, ignore this message.\r\n")
	_ = writer.Flush()
	return body.String()
}

var _ IdentityVerificationSender = (*SMTPIdentityVerificationSender)(nil)
