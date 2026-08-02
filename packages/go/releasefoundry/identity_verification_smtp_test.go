package releasefoundry

import (
	"bufio"
	"context"
	"crypto/tls"
	"encoding/base64"
	"errors"
	"io"
	"net"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"
)

func TestSMTPIdentityVerificationSenderDeliversEmail(t *testing.T) {
	clientConn, serverConn := net.Pipe()
	transcript := make(chan string, 1)
	go serveSMTPIdentityVerificationTest(serverConn, transcript)

	sender, err := NewSMTPIdentityVerificationSender(SMTPIdentityVerificationSenderOptions{
		Host: "localhost", Port: 465, From: "sender@example.test",
		AuthCode: "x", BrowserVerificationURL: "https://app.example.test/login/verify",
		Timeout: time.Second,
		DialTLS: func(context.Context, string, *tls.Config) (net.Conn, error) {
			return clientConn, nil
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	err = sender.SendIdentityVerification(context.Background(), IdentityVerificationDelivery{
		Channel: IdentityVerificationEmail, Destination: "recipient@example.test",
		ChallengeID: "ivc_444444444444444444444444444444444444",
		Code:        "314159", Purpose: IdentityVerificationBinding,
		ExpiresAt: time.Date(2026, 7, 10, 12, 30, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	message := <-transcript
	for _, expected := range []string{
		"From: sender@example.test",
		"To: recipient@example.test",
		"Subject: ReleaseFoundry verification code",
		"Your ReleaseFoundry verification code is: 314159",
		"https://app.example.test/login/verify?challenge_id=ivc_444444444444444444444444444444444444&amp;",
		"This code expires at 2026-07-10T12:30:00Z.",
	} {
		if strings.Contains(expected, "&amp;") {
			expected = strings.ReplaceAll(expected, "&amp;", "&")
		}
		if !strings.Contains(message, expected) {
			t.Fatalf("message did not contain %q: %q", expected, message)
		}
	}
	if strings.Contains(message, "recipient@example.test?") ||
		strings.Contains(message, "code=314159") {
		t.Fatalf("verification URL leaked raw delivery material: %q", message)
	}
}

func TestSMTPIdentityVerificationSenderRejectsUnsafeInput(t *testing.T) {
	valid := SMTPIdentityVerificationSenderOptions{
		Host: "smtp.example.test", Port: 465, From: "sender@example.test",
		AuthCode: "x",
	}
	for name, mutate := range map[string]func(*SMTPIdentityVerificationSenderOptions){
		"host": func(options *SMTPIdentityVerificationSenderOptions) { options.Host = "smtp.test\r\nX-Unsafe: yes" },
		"port": func(options *SMTPIdentityVerificationSenderOptions) { options.Port = 0 },
		"from": func(options *SMTPIdentityVerificationSenderOptions) {
			options.From = "sender@example.test\r\nBcc: unsafe@test"
		},
		"auth":       func(options *SMTPIdentityVerificationSenderOptions) { options.AuthCode = "" },
		"serverName": func(options *SMTPIdentityVerificationSenderOptions) { options.ServerName = "smtp.test\nunsafe" },
		"browserURL": func(options *SMTPIdentityVerificationSenderOptions) {
			options.BrowserVerificationURL = "https://app.example.test/login?next=/admin"
		},
	} {
		t.Run(name, func(t *testing.T) {
			options := valid
			mutate(&options)
			if _, err := NewSMTPIdentityVerificationSender(options); err == nil {
				t.Fatal("unsafe SMTP sender configuration was accepted")
			}
		})
	}
}

func TestSMTPIdentityVerificationSenderRejectsNonEmailAndUnsafeDelivery(t *testing.T) {
	dialed := false
	sender, err := NewSMTPIdentityVerificationSender(SMTPIdentityVerificationSenderOptions{
		Host: "smtp.example.test", Port: 465, From: "sender@example.test",
		AuthCode: "x",
		DialTLS: func(context.Context, string, *tls.Config) (net.Conn, error) {
			dialed = true
			return nil, errors.New("unexpected")
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, delivery := range []IdentityVerificationDelivery{
		{Channel: IdentityVerificationPhone, Destination: "recipient@example.test", Code: "123456"},
		{Channel: IdentityVerificationEmail, Destination: "recipient@example.test\r\nBcc: unsafe@test", Code: "123456"},
		{Channel: IdentityVerificationEmail, Destination: "recipient@example.test", Code: "12345\n"},
	} {
		if err := sender.SendIdentityVerification(context.Background(), delivery); err == nil {
			t.Fatal("unsafe SMTP delivery was accepted")
		}
	}
	if dialed {
		t.Fatal("sender dialed before validating delivery")
	}
}

func TestSMTPIdentityVerificationSenderRejectsUnsafeBrowserContextBeforeDial(t *testing.T) {
	dialed := false
	sender, err := NewSMTPIdentityVerificationSender(SMTPIdentityVerificationSenderOptions{
		Host: "smtp.example.test", Port: 465, From: "sender@example.test",
		AuthCode: "x", BrowserVerificationURL: "https://app.example.test/login/verify",
		DialTLS: func(context.Context, string, *tls.Config) (net.Conn, error) {
			dialed = true
			return nil, errors.New("unexpected")
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	for _, delivery := range []IdentityVerificationDelivery{
		{
			Channel: IdentityVerificationEmail, Destination: "recipient@example.test",
			Code: "123456", Purpose: IdentityVerificationLogin,
		},
		{
			ChallengeID: "ivc_444444444444444444444444444444444444",
			Channel:     IdentityVerificationEmail, Destination: "recipient@example.test",
			Code: "123456", Purpose: "signup",
		},
	} {
		if err := sender.SendIdentityVerification(context.Background(), delivery); err == nil {
			t.Fatal("unsafe browser context was accepted")
		}
	}
	if dialed {
		t.Fatal("sender dialed before validating browser context")
	}
}

func TestSMTPIdentityVerificationSenderRedactsProviderErrors(t *testing.T) {
	const sensitive = "provider-secret-and-recipient"
	authMarker := "smtp-" + "auth-marker"
	sender, err := NewSMTPIdentityVerificationSender(SMTPIdentityVerificationSenderOptions{
		Host: "smtp.example.test", Port: 465, From: "sender@example.test",
		AuthCode: authMarker,
		DialTLS: func(context.Context, string, *tls.Config) (net.Conn, error) {
			return nil, errors.New(sensitive)
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	err = sender.SendIdentityVerification(context.Background(), IdentityVerificationDelivery{
		Channel: IdentityVerificationEmail, Destination: "recipient@example.test", Code: "123456",
	})
	if err == nil || strings.Contains(err.Error(), sensitive) ||
		strings.Contains(err.Error(), "recipient@example.test") ||
		strings.Contains(err.Error(), authMarker) {
		t.Fatalf("SMTP error was not public-safe: %v", err)
	}
}

func TestSMTPIdentityVerificationSenderPassesTLSAndDeadlineControls(t *testing.T) {
	var address string
	var config *tls.Config
	clientConn, serverConn := net.Pipe()
	_ = serverConn.Close()
	sender, err := NewSMTPIdentityVerificationSender(SMTPIdentityVerificationSenderOptions{
		Host: "smtp.example.test", Port: 465, ServerName: "mail.example.test",
		From: "sender@example.test", AuthCode: "x",
		Timeout: 50 * time.Millisecond,
		DialTLS: func(_ context.Context, gotAddress string, gotConfig *tls.Config) (net.Conn, error) {
			address, config = gotAddress, gotConfig
			return clientConn, nil
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	_ = sender.SendIdentityVerification(context.Background(), IdentityVerificationDelivery{
		Channel: IdentityVerificationEmail, Destination: "recipient@example.test", Code: "123456",
	})
	if address != "smtp.example.test:465" {
		t.Fatalf("unexpected SMTP address %q", address)
	}
	if config == nil || config.ServerName != "mail.example.test" || config.MinVersion != tls.VersionTLS12 {
		t.Fatalf("unexpected TLS configuration: %#v", config)
	}
}

func TestSMTPIdentityVerificationSenderRealCalibration(t *testing.T) {
	if os.Getenv("RELEASEFOUNDRY_SMTP_REAL_CALIBRATION") != "1" {
		t.Skip("real SMTP calibration is opt-in")
	}
	host := os.Getenv("RELEASEFOUNDRY_SMTP_HOST")
	port, err := strconv.Atoi(os.Getenv("RELEASEFOUNDRY_SMTP_PORT"))
	if err != nil {
		t.Fatal("real SMTP calibration configuration is invalid")
	}
	from := os.Getenv("RELEASEFOUNDRY_SMTP_FROM")
	sender, err := NewSMTPIdentityVerificationSender(SMTPIdentityVerificationSenderOptions{
		Host: host, Port: port, From: from, AuthCode: os.Getenv("RELEASEFOUNDRY_SMTP_AUTH_CODE"),
		BrowserVerificationURL: os.Getenv("RELEASEFOUNDRY_IDENTITY_VERIFICATION_BROWSER_URL"),
		Timeout:                15 * time.Second,
	})
	if err != nil {
		t.Fatal("real SMTP calibration sender configuration was rejected")
	}
	if err := sender.SendIdentityVerification(context.Background(), IdentityVerificationDelivery{
		ChallengeID: "ivc_444444444444444444444444444444444444",
		Channel:     IdentityVerificationEmail, Destination: from, Code: "724190",
		Purpose: IdentityVerificationBinding, ExpiresAt: time.Now().UTC().Add(10 * time.Minute),
	}); err != nil {
		t.Fatalf("real SMTP calibration failed: %v", err)
	}
}

func serveSMTPIdentityVerificationTest(connection net.Conn, transcript chan<- string) {
	defer connection.Close()
	reader := bufio.NewReader(connection)
	writer := bufio.NewWriter(connection)
	writeSMTPTestReply(writer, "220 smtp.example.test ready")
	var message strings.Builder
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			transcript <- message.String()
			return
		}
		command := strings.TrimSpace(line)
		switch {
		case strings.HasPrefix(command, "EHLO"):
			writeSMTPTestReply(writer, "250-smtp.example.test", "250 AUTH PLAIN")
		case strings.HasPrefix(command, "AUTH PLAIN"):
			if fields := strings.Fields(command); len(fields) == 3 {
				_, _ = base64.StdEncoding.DecodeString(fields[2])
			}
			writeSMTPTestReply(writer, "235 authenticated")
		case strings.HasPrefix(command, "MAIL FROM:"):
			writeSMTPTestReply(writer, "250 sender accepted")
		case strings.HasPrefix(command, "RCPT TO:"):
			writeSMTPTestReply(writer, "250 recipient accepted")
		case command == "DATA":
			writeSMTPTestReply(writer, "354 continue")
			data := bufio.NewReader(reader)
			for {
				dataLine, dataErr := data.ReadString('\n')
				if dataErr != nil {
					transcript <- message.String()
					return
				}
				if dataLine == ".\r\n" {
					break
				}
				message.WriteString(dataLine)
			}
			writeSMTPTestReply(writer, "250 queued")
		case command == "QUIT":
			writeSMTPTestReply(writer, "221 bye")
			transcript <- message.String()
			return
		default:
			writeSMTPTestReply(writer, "500 unsupported")
		}
	}
}

func writeSMTPTestReply(writer *bufio.Writer, lines ...string) {
	for _, line := range lines {
		_, _ = io.WriteString(writer, line+"\r\n")
	}
	_ = writer.Flush()
}
