package releasefoundry

import (
	"bytes"
	"context"
	"database/sql/driver"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"reflect"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/lib/pq"
)

const (
	postgresOAuthFirstLoginOrganizationID = "11111111-1111-4111-8111-111111111111"
	postgresOAuthFirstLoginProjectID      = "22222222-2222-4222-8222-222222222222"
	postgresOAuthFirstLoginSessionID      = "33333333-3333-4333-8333-333333333333"
	postgresOAuthFirstLoginPrincipalID    = "44444444-4444-4444-8444-444444444444"
	postgresOAuthFirstLoginCredentialID   = "55555555-5555-4555-8555-555555555555"
	postgresOAuthFirstLoginConnectionID   = "66666666-6666-4666-8666-666666666666"
	postgresOAuthFirstLoginTokenRefID     = "77777777-7777-4777-8777-777777777777"
)

type postgresOAuthFirstLoginCountingReader struct {
	reader    io.Reader
	bytesRead int
}

func (reader *postgresOAuthFirstLoginCountingReader) Read(destination []byte) (int, error) {
	count, err := reader.reader.Read(destination)
	reader.bytesRead += count
	return count, err
}

type postgresOAuthFirstLoginCapturedArgument struct {
	value driver.Value
}

func (argument *postgresOAuthFirstLoginCapturedArgument) Match(value driver.Value) bool {
	argument.value = value
	return true
}

func newPostgresOAuthFirstLoginCapturedArguments() (
	[]driver.Value,
	[]*postgresOAuthFirstLoginCapturedArgument,
) {
	captured := make([]*postgresOAuthFirstLoginCapturedArgument, 17)
	arguments := make([]driver.Value, len(captured))
	for index := range captured {
		captured[index] = &postgresOAuthFirstLoginCapturedArgument{}
		arguments[index] = captured[index]
	}
	return arguments, captured
}

func postgresOAuthFirstLoginCapturedValues(
	captured []*postgresOAuthFirstLoginCapturedArgument,
) []driver.Value {
	values := make([]driver.Value, len(captured))
	for index := range captured {
		values[index] = captured[index].value
	}
	return values
}

func newPostgresOAuthFirstLoginTestStore(
	t *testing.T,
	now time.Time,
	random io.Reader,
	previousLookup []IdentityLifecycleLookupKey,
) (*ProductionIdentityStore, sqlmock.Sqlmock) {
	t.Helper()
	db, mock, err := sqlmock.New(
		sqlmock.QueryMatcherOption(sqlmock.QueryMatcherRegexp),
	)
	if err != nil {
		t.Fatal(err)
	}
	store, err := NewProductionIdentityStore(ProductionIdentityStoreOptions{
		DB:                                 db,
		SessionKey:                         bytes.Repeat([]byte{0x31}, 32),
		SessionKeyVersion:                  "session-v2",
		Random:                             random,
		Now:                                func() time.Time { return now },
		SQLTimeout:                         time.Second,
		StatementTimeout:                   800 * time.Millisecond,
		LockTimeout:                        200 * time.Millisecond,
		LifecycleReceiptKey:                bytes.Repeat([]byte{0x41}, 32),
		LifecycleReceiptKeyVersion:         "receipt-v2",
		LifecycleReceiptLookupKey:          bytes.Repeat([]byte{0x51}, 32),
		LifecycleReceiptLookupKeyVersion:   "lookup-v2",
		PreviousLifecycleReceiptLookupKeys: previousLookup,
	})
	if err != nil {
		_ = db.Close()
		t.Fatal(err)
	}
	t.Cleanup(func() { _ = store.Close() })
	return store, mock
}

func newPostgresOAuthFirstLoginTestCoordinator(
	t *testing.T,
	now time.Time,
	random io.Reader,
	previousLookup []IdentityLifecycleLookupKey,
) (*PostgresOAuthFirstLoginCoordinator, *ProductionIdentityStore, sqlmock.Sqlmock) {
	t.Helper()
	store, mock := newPostgresOAuthFirstLoginTestStore(
		t,
		now,
		random,
		previousLookup,
	)
	coordinator, err := NewPostgresOAuthFirstLoginCoordinator(
		PostgresOAuthFirstLoginCoordinatorOptions{
			Store:          store,
			OrganizationID: postgresOAuthFirstLoginOrganizationID,
			ProjectID:      postgresOAuthFirstLoginProjectID,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	return coordinator, store, mock
}

func validPostgresOAuthFirstLoginCommand(
	now time.Time,
) OAuthFirstLoginCompletionCommand {
	return OAuthFirstLoginCompletionCommand{
		SchemaVersion:   OAuthFirstLoginSchemaVersion,
		Purpose:         OAuthPurposeFirstLogin,
		OrganizationID:  postgresOAuthFirstLoginOrganizationID,
		ProjectID:       postgresOAuthFirstLoginProjectID,
		Provider:        "google",
		ProviderSubject: "google-subject-12345",
		DisplayName:     "Example Account",
		VerifiedEmail:   "person@example.cn",
		TokenRef:        "vault:oauth-first-login-test-reference",
		CompletedAt:     now,
	}
}

func postgresOAuthFirstLoginCompletionRows(
	command OAuthFirstLoginCompletionCommand,
	accessExpiresAt time.Time,
	refreshExpiresAt time.Time,
	created bool,
) *sqlmock.Rows {
	return sqlmock.NewRows([]string{
		"session_id",
		"principal_id",
		"credential_id",
		"connection_id",
		"token_ref_id",
		"created",
		"organization_id",
		"project_id",
		"provider_name",
		"access_expires_at",
		"refresh_expires_at",
		"completed_at",
	}).AddRow(
		postgresOAuthFirstLoginSessionID,
		postgresOAuthFirstLoginPrincipalID,
		postgresOAuthFirstLoginCredentialID,
		postgresOAuthFirstLoginConnectionID,
		postgresOAuthFirstLoginTokenRefID,
		created,
		command.OrganizationID,
		command.ProjectID,
		command.Provider,
		accessExpiresAt,
		refreshExpiresAt,
		command.CompletedAt,
	)
}

func expectPostgresOAuthFirstLoginTransactionPrefix(mock sqlmock.Sqlmock) {
	mock.ExpectBegin()
	mock.ExpectExec(regexp.QuoteMeta("SELECT set_config('statement_timeout'")).
		WithArgs("800ms", "200ms").
		WillReturnResult(sqlmock.NewResult(0, 1))
	mock.ExpectExec(regexp.QuoteMeta("SELECT set_config('app.a1_organization_id'")).
		WithArgs(
			postgresOAuthFirstLoginOrganizationID,
			postgresOAuthFirstLoginProjectID,
		).
		WillReturnResult(sqlmock.NewResult(0, 1))
}

func expectPostgresOAuthFirstLoginCompletionQuery(
	mock sqlmock.Sqlmock,
	arguments []driver.Value,
	rows *sqlmock.Rows,
	queryError error,
) {
	expectation := mock.ExpectQuery(
		regexp.QuoteMeta("FROM a1_complete_oauth_first_login_with_refresh("),
	).WithArgs(arguments...)
	if queryError != nil {
		expectation.WillReturnError(queryError)
		return
	}
	expectation.WillReturnRows(rows)
}

func requirePostgresOAuthFirstLoginError(
	t *testing.T,
	err error,
	status int,
	code string,
) OAuthError {
	t.Helper()
	var oauthError OAuthError
	if !errors.As(err, &oauthError) {
		t.Fatalf("expected OAuthError, got %T: %v", err, err)
	}
	if oauthError.Status != status || oauthError.Code != code {
		t.Fatalf(
			"unexpected OAuth error status=%d code=%q message=%q",
			oauthError.Status,
			oauthError.Code,
			oauthError.Message,
		)
	}
	if oauthError.Cause != nil {
		t.Fatalf("public PostgreSQL OAuth error retained internal cause: %v", oauthError.Cause)
	}
	return oauthError
}

func scanPostgresOAuthFirstLoginArray(
	t *testing.T,
	value driver.Value,
) []string {
	t.Helper()
	var values pq.StringArray
	if err := values.Scan(value); err != nil {
		t.Fatalf("scan PostgreSQL text array %#v: %v", value, err)
	}
	return append([]string(nil), values...)
}

func TestPostgresOAuthFirstLoginCoordinatorConstructor(t *testing.T) {
	now := time.Date(2026, 7, 23, 10, 0, 0, 0, time.UTC)
	validStore, _ := newPostgresOAuthFirstLoginTestStore(
		t,
		now,
		bytes.NewReader(bytes.Repeat([]byte{0x61}, 128)),
		nil,
	)
	validOptions := PostgresOAuthFirstLoginCoordinatorOptions{
		Store:          validStore,
		OrganizationID: postgresOAuthFirstLoginOrganizationID,
		ProjectID:      postgresOAuthFirstLoginProjectID,
	}
	coordinator, err := NewPostgresOAuthFirstLoginCoordinator(validOptions)
	if err != nil {
		t.Fatalf("construct valid coordinator: %v", err)
	}
	if coordinator.accessTTL != defaultIdentityAccessSessionTTL ||
		coordinator.refreshTTL != defaultIdentityRefreshSessionTTL {
		t.Fatalf(
			"unexpected default TTLs access=%s refresh=%s",
			coordinator.accessTTL,
			coordinator.refreshTTL,
		)
	}

	db := validStore.db
	codec := validStore.sessionTokens
	ring := validStore.lifecycleKeys
	validNow := validStore.now
	for name, store := range map[string]*ProductionIdentityStore{
		"nil store": nil,
		"nil database": {
			sessionTokens: codec,
			lifecycleKeys: ring,
			now:           validNow,
		},
		"nil session codec": {
			db:            db,
			lifecycleKeys: ring,
			now:           validNow,
		},
		"nil lifecycle lookup keyring": {
			db:            db,
			sessionTokens: codec,
			now:           validNow,
		},
		"nil clock": {
			db:            db,
			sessionTokens: codec,
			lifecycleKeys: ring,
		},
	} {
		t.Run(name, func(t *testing.T) {
			options := validOptions
			options.Store = store
			if _, err := NewPostgresOAuthFirstLoginCoordinator(options); err == nil {
				t.Fatal("expected constructor rejection")
			}
		})
	}

	for name, mutate := range map[string]func(*PostgresOAuthFirstLoginCoordinatorOptions){
		"organization leading space": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.OrganizationID = " " + postgresOAuthFirstLoginOrganizationID
		},
		"organization noncanonical UUID": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.OrganizationID = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
		},
		"project trailing space": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.ProjectID += " "
		},
		"project noncanonical UUID": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.ProjectID = "BBBBBBBB-BBBB-4BBB-8BBB-BBBBBBBBBBBB"
		},
		"access too short": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.AccessTTL = time.Minute - time.Nanosecond
		},
		"access too long": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.AccessTTL = 7*24*time.Hour + time.Nanosecond
		},
		"refresh equal to access": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.AccessTTL = time.Hour
			options.RefreshTTL = time.Hour
		},
		"refresh too long": func(options *PostgresOAuthFirstLoginCoordinatorOptions) {
			options.RefreshTTL = 366*24*time.Hour + time.Nanosecond
		},
	} {
		t.Run(name, func(t *testing.T) {
			options := validOptions
			mutate(&options)
			if _, err := NewPostgresOAuthFirstLoginCoordinator(options); err == nil {
				t.Fatal("expected constructor rejection")
			}
		})
	}

	t.Run("empty lookup keyring", func(t *testing.T) {
		validStore.lifecycleKeys.mu.Lock()
		original := validStore.lifecycleKeys.lookupKeys
		validStore.lifecycleKeys.lookupKeys = map[string][]byte{}
		validStore.lifecycleKeys.mu.Unlock()
		t.Cleanup(func() {
			validStore.lifecycleKeys.mu.Lock()
			validStore.lifecycleKeys.lookupKeys = original
			validStore.lifecycleKeys.mu.Unlock()
		})
		if _, err := NewPostgresOAuthFirstLoginCoordinator(validOptions); err == nil {
			t.Fatal("expected empty lookup keyring rejection")
		}
	})

	t.Run("oversized lookup keyring", func(t *testing.T) {
		validStore.lifecycleKeys.mu.Lock()
		original := validStore.lifecycleKeys.lookupKeys
		oversized := make(map[string][]byte, maxPostgresOAuthFirstLoginLookupDigests+1)
		for index := 0; index <= maxPostgresOAuthFirstLoginLookupDigests; index++ {
			oversized[fmt.Sprintf("lookup-%02d", index)] =
				bytes.Repeat([]byte{byte(index + 1)}, 32)
		}
		validStore.lifecycleKeys.lookupKeys = oversized
		validStore.lifecycleKeys.mu.Unlock()
		t.Cleanup(func() {
			validStore.lifecycleKeys.mu.Lock()
			validStore.lifecycleKeys.lookupKeys = original
			validStore.lifecycleKeys.mu.Unlock()
		})
		if _, err := NewPostgresOAuthFirstLoginCoordinator(validOptions); err == nil {
			t.Fatal("expected oversized lookup keyring rejection")
		}
	})
}

func TestPostgresOAuthFirstLoginCoordinatorRejectsInvalidCommandBeforeRandomOrSQL(
	t *testing.T,
) {
	now := time.Date(2026, 7, 23, 10, 30, 0, 0, time.UTC)
	testCases := map[string]func(*OAuthFirstLoginCompletionCommand){
		"schema": func(command *OAuthFirstLoginCompletionCommand) {
			command.SchemaVersion = "releasefoundry.oauth_first_login.v0"
		},
		"purpose": func(command *OAuthFirstLoginCompletionCommand) {
			command.Purpose = "bind"
		},
		"organization": func(command *OAuthFirstLoginCompletionCommand) {
			command.OrganizationID = postgresOAuthFirstLoginProjectID
		},
		"project": func(command *OAuthFirstLoginCompletionCommand) {
			command.ProjectID = postgresOAuthFirstLoginOrganizationID
		},
		"provider uppercase": func(command *OAuthFirstLoginCompletionCommand) {
			command.Provider = "Google"
		},
		"provider unsupported": func(command *OAuthFirstLoginCompletionCommand) {
			command.Provider = "wechat"
		},
		"subject empty": func(command *OAuthFirstLoginCompletionCommand) {
			command.ProviderSubject = ""
		},
		"subject whitespace": func(command *OAuthFirstLoginCompletionCommand) {
			command.ProviderSubject = " subject"
		},
		"subject control": func(command *OAuthFirstLoginCompletionCommand) {
			command.ProviderSubject = "subject\vcontrol"
		},
		"subject too long": func(command *OAuthFirstLoginCompletionCommand) {
			command.ProviderSubject = strings.Repeat("s", 1025)
		},
		"email malformed": func(command *OAuthFirstLoginCompletionCommand) {
			command.VerifiedEmail = "not-an-email"
		},
		"email noncanonical": func(command *OAuthFirstLoginCompletionCommand) {
			command.VerifiedEmail = "Person@Example.CN"
		},
		"email too long": func(command *OAuthFirstLoginCompletionCommand) {
			command.VerifiedEmail = strings.Repeat("a", 310) + "@example.cn"
		},
		"token reference blank": func(command *OAuthFirstLoginCompletionCommand) {
			command.TokenRef = ""
		},
		"token reference not opaque": func(command *OAuthFirstLoginCompletionCommand) {
			command.TokenRef = "plain-reference"
		},
		"token reference whitespace": func(command *OAuthFirstLoginCompletionCommand) {
			command.TokenRef += " "
		},
		"token reference control": func(command *OAuthFirstLoginCompletionCommand) {
			command.TokenRef = "vault:reference\vcontrol"
		},
		"display leading space": func(command *OAuthFirstLoginCompletionCommand) {
			command.DisplayName = " Account"
		},
		"display control": func(command *OAuthFirstLoginCompletionCommand) {
			command.DisplayName = "Account\u0085Name"
		},
		"display too long": func(command *OAuthFirstLoginCompletionCommand) {
			command.DisplayName = strings.Repeat("d", 257)
		},
		"completion zero": func(command *OAuthFirstLoginCompletionCommand) {
			command.CompletedAt = time.Time{}
		},
		"completion non UTC": func(command *OAuthFirstLoginCompletionCommand) {
			command.CompletedAt = time.Date(
				2026,
				7,
				23,
				18,
				30,
				0,
				0,
				time.FixedZone("CST", 8*60*60),
			)
		},
		"completion too old": func(command *OAuthFirstLoginCompletionCommand) {
			command.CompletedAt = now.Add(
				-maxPostgresOAuthFirstLoginCompletionAge - time.Nanosecond,
			)
		},
		"completion too far future": func(command *OAuthFirstLoginCompletionCommand) {
			command.CompletedAt = now.Add(
				maxPostgresOAuthFirstLoginCompletionSkew + time.Nanosecond,
			)
		},
	}
	for name, mutate := range testCases {
		t.Run(name, func(t *testing.T) {
			random := &postgresOAuthFirstLoginCountingReader{
				reader: bytes.NewReader(bytes.Repeat([]byte{0x71}, 128)),
			}
			coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
				t,
				now,
				random,
				nil,
			)
			command := validPostgresOAuthFirstLoginCommand(now)
			mutate(&command)
			result, receipt, err := coordinator.CompleteOAuthFirstLogin(
				context.Background(),
				command,
			)
			requirePostgresOAuthFirstLoginError(
				t,
				err,
				http.StatusBadRequest,
				"oauth_first_login_completion_invalid",
			)
			if result != (OAuthFirstLoginCompletionResult{}) ||
				receipt.SessionID() != "" ||
				random.bytesRead != 0 {
				t.Fatalf(
					"invalid command escaped validation result=%#v receipt=%v random_bytes=%d",
					result,
					receipt,
					random.bytesRead,
				)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresOAuthFirstLoginCoordinatorRejectsNilContextWithoutRandomOrSQL(
	t *testing.T,
) {
	now := time.Date(2026, 7, 23, 10, 45, 0, 0, time.UTC)
	random := &postgresOAuthFirstLoginCountingReader{
		reader: bytes.NewReader(bytes.Repeat([]byte{0x72}, 128)),
	}
	coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
		t,
		now,
		random,
		nil,
	)
	_, receipt, err := coordinator.CompleteOAuthFirstLogin(
		nil,
		validPostgresOAuthFirstLoginCommand(now),
	)
	requirePostgresOAuthFirstLoginError(
		t,
		err,
		http.StatusServiceUnavailable,
		"oauth_first_login_unavailable",
	)
	if receipt.SessionID() != "" || random.bytesRead != 0 {
		t.Fatalf(
			"nil context generated material receipt=%v random_bytes=%d",
			receipt,
			random.bytesRead,
		)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthFirstLoginCoordinatorUsesKeyedSQLAndOneUseReceipt(
	t *testing.T,
) {
	now := time.Date(2026, 7, 23, 11, 0, 0, 0, time.UTC)
	accessNonce := bytes.Repeat([]byte{0x81}, identitySessionNonceBytes)
	refreshNonce := bytes.Repeat([]byte{0x82}, identitySessionNonceBytes)
	random := &postgresOAuthFirstLoginCountingReader{
		reader: bytes.NewReader(append(accessNonce, refreshNonce...)),
	}
	previousLookup := []IdentityLifecycleLookupKey{{
		Version: "lookup-v1",
		Key:     bytes.Repeat([]byte{0x52}, 32),
	}}
	coordinator, store, mock := newPostgresOAuthFirstLoginTestCoordinator(
		t,
		now,
		random,
		previousLookup,
	)
	command := validPostgresOAuthFirstLoginCommand(now)
	accessExpiresAt := now.Add(defaultIdentityAccessSessionTTL)
	refreshExpiresAt := now.Add(defaultIdentityRefreshSessionTTL)
	arguments, captured := newPostgresOAuthFirstLoginCapturedArguments()
	expectPostgresOAuthFirstLoginTransactionPrefix(mock)
	expectPostgresOAuthFirstLoginCompletionQuery(
		mock,
		arguments,
		postgresOAuthFirstLoginCompletionRows(
			command,
			accessExpiresAt,
			refreshExpiresAt,
			true,
		),
		nil,
	)
	mock.ExpectCommit()

	result, receipt, err := coordinator.CompleteOAuthFirstLogin(
		context.Background(),
		command,
	)
	if err != nil {
		t.Fatalf("complete first login: %v", err)
	}
	if result.SchemaVersion != OAuthFirstLoginSchemaVersion ||
		result.Provider != command.Provider ||
		result.AccountID != postgresOAuthFirstLoginPrincipalID ||
		result.CredentialID != postgresOAuthFirstLoginCredentialID ||
		result.SessionID != postgresOAuthFirstLoginSessionID ||
		!result.Created ||
		!result.CompletedAt.Equal(command.CompletedAt) {
		t.Fatalf("unexpected completion result: %#v", result)
	}
	if receipt.SessionID() != postgresOAuthFirstLoginSessionID ||
		receipt.KeyVersion() != "session-v2" ||
		receipt.RefreshKeyVersion() != "session-v2" ||
		!receipt.ExpiresAt().Equal(accessExpiresAt) ||
		!receipt.RefreshExpiresAt().Equal(refreshExpiresAt) {
		t.Fatalf("unexpected issuance receipt: %v", receipt)
	}

	values := postgresOAuthFirstLoginCapturedValues(captured)
	if values[0] != command.OrganizationID ||
		values[1] != command.ProjectID ||
		values[2] != command.Provider ||
		values[5] != command.TokenRef ||
		values[15] != command.DisplayName {
		t.Fatalf("unexpected public SQL arguments: %#v", values)
	}
	expectedSubjectDigests := store.lifecycleKeys.receiptDigests(strings.Join(
		[]string{
			"oauth-first-login",
			"provider-subject",
			command.Provider,
			command.ProviderSubject,
		},
		"\x00",
	))
	expectedEmailDigests := store.lifecycleKeys.receiptDigests(strings.Join(
		[]string{
			"oauth-first-login",
			"verified-email",
			command.VerifiedEmail,
		},
		"\x00",
	))
	if actual := scanPostgresOAuthFirstLoginArray(t, values[3]); !reflect.DeepEqual(actual, expectedSubjectDigests) {
		t.Fatalf(
			"unexpected subject digest candidates actual=%v expected=%v",
			actual,
			expectedSubjectDigests,
		)
	}
	if actual := scanPostgresOAuthFirstLoginArray(t, values[4]); !reflect.DeepEqual(actual, expectedEmailDigests) {
		t.Fatalf(
			"unexpected email digest candidates actual=%v expected=%v",
			actual,
			expectedEmailDigests,
		)
	}
	if len(expectedSubjectDigests) != 2 || len(expectedEmailDigests) != 2 {
		t.Fatalf(
			"retained lookup key was not represented subject=%d email=%d",
			len(expectedSubjectDigests),
			len(expectedEmailDigests),
		)
	}
	for _, index := range []int{6, 7, 8, 9, 10, 13, 14} {
		value, ok := values[index].(string)
		if !ok || len(value) != 64 {
			t.Fatalf("SQL digest argument %d is not a SHA-256 hex digest: %#v", index, values[index])
		}
	}
	if value, ok := values[11].(time.Time); !ok || !value.Equal(accessExpiresAt) {
		t.Fatalf("unexpected access expiry SQL argument: %#v", values[11])
	}
	if value, ok := values[12].(time.Time); !ok || !value.Equal(refreshExpiresAt) {
		t.Fatalf("unexpected refresh expiry SQL argument: %#v", values[12])
	}
	var metadata map[string]string
	if err := json.Unmarshal([]byte(values[16].(string)), &metadata); err != nil {
		t.Fatalf("decode metadata: %v", err)
	}
	if !reflect.DeepEqual(metadata, map[string]string{
		"source":                      "oauth_first_login",
		"provider":                    command.Provider,
		"session_key_version":         "session-v2",
		"identity_lookup_key_version": "lookup-v2",
	}) {
		t.Fatalf("unexpected public metadata: %#v", metadata)
	}

	encodedReceipt, err := json.Marshal(receipt)
	if err != nil {
		t.Fatal(err)
	}
	if string(encodedReceipt) != "{}" {
		t.Fatalf("receipt exposed fields through JSON: %s", encodedReceipt)
	}
	renderedReceipt := fmt.Sprintf("%v %#v", receipt, receipt)
	accessBearer, refreshBearer, err := receipt.TakeBearerTokens()
	if err != nil {
		t.Fatalf("take bearer pair: %v", err)
	}
	if !strings.HasPrefix(accessBearer, identitySessionBearerPrefix+".session-v2.") ||
		!strings.HasPrefix(refreshBearer, identityRefreshBearerPrefix+".session-v2.") {
		t.Fatalf(
			"unexpected bearer classes access_prefix=%t refresh_prefix=%t",
			strings.HasPrefix(accessBearer, identitySessionBearerPrefix+".session-v2."),
			strings.HasPrefix(refreshBearer, identityRefreshBearerPrefix+".session-v2."),
		)
	}
	if strings.Contains(renderedReceipt, accessBearer) ||
		strings.Contains(renderedReceipt, refreshBearer) {
		t.Fatal("receipt formatter exposed bearer material")
	}
	accessDigest, accessVersion, err := store.sessionTokens.digest(accessBearer)
	if err != nil {
		t.Fatal(err)
	}
	refreshDigest, refreshVersion, err := store.sessionTokens.digestRefresh(refreshBearer)
	if err != nil {
		t.Fatal(err)
	}
	if values[8] != accessDigest ||
		values[9] != refreshDigest ||
		accessVersion != "session-v2" ||
		refreshVersion != "session-v2" {
		t.Fatalf(
			"bearer digests did not match keyed SQL arguments access=%t refresh=%t",
			values[8] == accessDigest,
			values[9] == refreshDigest,
		)
	}
	for index, value := range values {
		if index == 5 {
			continue
		}
		rendered := fmt.Sprint(value)
		for name, sensitive := range map[string]string{
			"provider subject": command.ProviderSubject,
			"verified email":   command.VerifiedEmail,
			"access bearer":    accessBearer,
			"refresh bearer":   refreshBearer,
		} {
			if strings.Contains(rendered, sensitive) {
				t.Fatalf("SQL argument %d exposed %s", index, name)
			}
		}
	}
	if secondAccess, secondRefresh, err := receipt.TakeBearerTokens(); !errors.Is(err, ErrIdentitySessionBearerTaken) ||
		secondAccess != "" ||
		secondRefresh != "" {
		t.Fatalf(
			"receipt returned bearer pair twice access_nonempty=%t refresh_nonempty=%t err=%v",
			secondAccess != "",
			secondRefresh != "",
			err,
		)
	}
	if random.bytesRead != 2*identitySessionNonceBytes {
		t.Fatalf("unexpected random consumption: %d", random.bytesRead)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestPostgresOAuthFirstLoginCoordinatorRetriesWithIdenticalMaterial(
	t *testing.T,
) {
	for _, code := range []string{"40001", "40P01"} {
		t.Run(code, func(t *testing.T) {
			now := time.Date(2026, 7, 23, 11, 30, 0, 0, time.UTC)
			random := &postgresOAuthFirstLoginCountingReader{
				reader: bytes.NewReader(bytes.Repeat(
					[]byte{0x91},
					2*identitySessionNonceBytes,
				)),
			}
			coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
				t,
				now,
				random,
				nil,
			)
			command := validPostgresOAuthFirstLoginCommand(now)
			firstArguments, firstCaptured :=
				newPostgresOAuthFirstLoginCapturedArguments()
			secondArguments, secondCaptured :=
				newPostgresOAuthFirstLoginCapturedArguments()

			expectPostgresOAuthFirstLoginTransactionPrefix(mock)
			expectPostgresOAuthFirstLoginCompletionQuery(
				mock,
				firstArguments,
				nil,
				&pq.Error{
					Code:    pq.ErrorCode(code),
					Message: "retryable transaction failure",
				},
			)
			mock.ExpectRollback()
			expectPostgresOAuthFirstLoginTransactionPrefix(mock)
			expectPostgresOAuthFirstLoginCompletionQuery(
				mock,
				secondArguments,
				postgresOAuthFirstLoginCompletionRows(
					command,
					now.Add(defaultIdentityAccessSessionTTL),
					now.Add(defaultIdentityRefreshSessionTTL),
					false,
				),
				nil,
			)
			mock.ExpectCommit()

			result, receipt, err := coordinator.CompleteOAuthFirstLogin(
				context.Background(),
				command,
			)
			if err != nil {
				t.Fatalf("retry completion: %v", err)
			}
			if result.Created || receipt.SessionID() != postgresOAuthFirstLoginSessionID {
				t.Fatalf("unexpected retry result=%#v receipt=%v", result, receipt)
			}
			if !reflect.DeepEqual(
				postgresOAuthFirstLoginCapturedValues(firstCaptured),
				postgresOAuthFirstLoginCapturedValues(secondCaptured),
			) {
				t.Fatal("transaction retry regenerated or changed prepared material")
			}
			if random.bytesRead != 2*identitySessionNonceBytes {
				t.Fatalf(
					"retry consumed %d random bytes instead of one bearer pair",
					random.bytesRead,
				)
			}
			if _, _, err := receipt.TakeBearerTokens(); err != nil {
				t.Fatalf("retry receipt was not usable: %v", err)
			}
			if err := mock.ExpectationsWereMet(); err != nil {
				t.Fatal(err)
			}
		})
	}
}

func TestPostgresOAuthFirstLoginCoordinatorRetryExhaustionIsNonDisclosing(
	t *testing.T,
) {
	now := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	random := &postgresOAuthFirstLoginCountingReader{
		reader: bytes.NewReader(bytes.Repeat(
			[]byte{0xa1},
			2*identitySessionNonceBytes,
		)),
	}
	coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
		t,
		now,
		random,
		nil,
	)
	command := validPostgresOAuthFirstLoginCommand(now)
	for attempt := 0; attempt < maxPostgresOAuthFirstLoginAttempts; attempt++ {
		arguments, _ := newPostgresOAuthFirstLoginCapturedArguments()
		expectPostgresOAuthFirstLoginTransactionPrefix(mock)
		expectPostgresOAuthFirstLoginCompletionQuery(
			mock,
			arguments,
			nil,
			&pq.Error{
				Code: pq.ErrorCode("40001"),
				Message: "driver relation oauth_first_login_operations contains " +
					command.ProviderSubject,
			},
		)
		mock.ExpectRollback()
	}
	result, receipt, err := coordinator.CompleteOAuthFirstLogin(
		context.Background(),
		command,
	)
	oauthError := requirePostgresOAuthFirstLoginError(
		t,
		err,
		http.StatusServiceUnavailable,
		"oauth_first_login_unavailable",
	)
	if result != (OAuthFirstLoginCompletionResult{}) ||
		receipt.SessionID() != "" ||
		random.bytesRead != 2*identitySessionNonceBytes ||
		strings.Contains(oauthError.Error(), command.ProviderSubject) ||
		strings.Contains(oauthError.Error(), "oauth_first_login_operations") {
		t.Fatalf(
			"retry exhaustion leaked or returned material result=%#v receipt=%v bytes=%d error=%q",
			result,
			receipt,
			random.bytesRead,
			oauthError.Error(),
		)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatal(err)
	}
}

func TestMapPostgresOAuthFirstLoginError(t *testing.T) {
	for name, testCase := range map[string]struct {
		err    error
		status int
		code   string
	}{
		"canonical email conflict": {
			err: &pq.Error{
				Code:    pq.ErrorCode("23505"),
				Message: "canonical_email_conflict",
			},
			status: http.StatusConflict,
			code:   "oauth_first_login_email_conflict",
		},
		"idempotency conflict": {
			err: &pq.Error{
				Code:    pq.ErrorCode("23505"),
				Message: "idempotency_conflict",
			},
			status: http.StatusConflict,
			code:   "oauth_first_login_replay_conflict",
		},
		"credential conflict": {
			err: &pq.Error{
				Code:    pq.ErrorCode("23505"),
				Message: "provider_subject_conflict",
			},
			status: http.StatusConflict,
			code:   "oauth_first_login_conflict",
		},
		"authorization": {
			err: &pq.Error{
				Code:    pq.ErrorCode("42501"),
				Message: "trusted scope rejected",
			},
			status: http.StatusForbidden,
			code:   "oauth_first_login_not_authorized",
		},
		"invalid state": {
			err: &pq.Error{
				Code:    pq.ErrorCode("22023"),
				Message: "malformed completion",
			},
			status: http.StatusBadRequest,
			code:   "oauth_first_login_completion_invalid",
		},
		"generic PostgreSQL": {
			err: &pq.Error{
				Code:    pq.ErrorCode("XX000"),
				Message: "internal relation detail",
			},
			status: http.StatusServiceUnavailable,
			code:   "oauth_first_login_unavailable",
		},
		"generic driver": {
			err:    errors.New("raw driver detail"),
			status: http.StatusServiceUnavailable,
			code:   "oauth_first_login_unavailable",
		},
	} {
		t.Run(name, func(t *testing.T) {
			mapped := mapPostgresOAuthFirstLoginError(testCase.err)
			oauthError := requirePostgresOAuthFirstLoginError(
				t,
				mapped,
				testCase.status,
				testCase.code,
			)
			if strings.Contains(oauthError.Error(), "relation") ||
				strings.Contains(oauthError.Error(), "driver") {
				t.Fatalf("mapped error disclosed driver detail: %v", oauthError)
			}
		})
	}
	if mapPostgresOAuthFirstLoginError(nil) != nil {
		t.Fatal("nil error did not remain nil")
	}
}

func TestPostgresOAuthFirstLoginCoordinatorTransactionFailuresReturnNoReceipt(
	t *testing.T,
) {
	now := time.Date(2026, 7, 23, 12, 30, 0, 0, time.UTC)
	command := validPostgresOAuthFirstLoginCommand(now)

	t.Run("begin", func(t *testing.T) {
		random := &postgresOAuthFirstLoginCountingReader{
			reader: bytes.NewReader(bytes.Repeat(
				[]byte{0xb1},
				2*identitySessionNonceBytes,
			)),
		}
		coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
			t,
			now,
			random,
			nil,
		)
		mock.ExpectBegin().WillReturnError(errors.New("begin failed"))
		_, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		requirePostgresOAuthFirstLoginError(
			t,
			err,
			http.StatusServiceUnavailable,
			"oauth_first_login_unavailable",
		)
		if receipt.SessionID() != "" {
			t.Fatalf("begin failure returned receipt: %v", receipt)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("transaction configuration", func(t *testing.T) {
		coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
			t,
			now,
			bytes.NewReader(bytes.Repeat(
				[]byte{0xb2},
				2*identitySessionNonceBytes,
			)),
			nil,
		)
		mock.ExpectBegin()
		mock.ExpectExec(regexp.QuoteMeta("SELECT set_config('statement_timeout'")).
			WithArgs("800ms", "200ms").
			WillReturnError(errors.New("configuration failed"))
		mock.ExpectRollback()
		_, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		requirePostgresOAuthFirstLoginError(
			t,
			err,
			http.StatusServiceUnavailable,
			"oauth_first_login_unavailable",
		)
		if receipt.SessionID() != "" {
			t.Fatalf("configuration failure returned receipt: %v", receipt)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("trusted scope", func(t *testing.T) {
		coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
			t,
			now,
			bytes.NewReader(bytes.Repeat(
				[]byte{0xb3},
				2*identitySessionNonceBytes,
			)),
			nil,
		)
		mock.ExpectBegin()
		mock.ExpectExec(regexp.QuoteMeta("SELECT set_config('statement_timeout'")).
			WithArgs("800ms", "200ms").
			WillReturnResult(sqlmock.NewResult(0, 1))
		mock.ExpectExec(regexp.QuoteMeta("SELECT set_config('app.a1_organization_id'")).
			WithArgs(
				postgresOAuthFirstLoginOrganizationID,
				postgresOAuthFirstLoginProjectID,
			).
			WillReturnError(&pq.Error{
				Code:    pq.ErrorCode("42501"),
				Message: "scope denied",
			})
		mock.ExpectRollback()
		_, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		requirePostgresOAuthFirstLoginError(
			t,
			err,
			http.StatusForbidden,
			"oauth_first_login_not_authorized",
		)
		if receipt.SessionID() != "" {
			t.Fatalf("scope failure returned receipt: %v", receipt)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("query conflict", func(t *testing.T) {
		coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
			t,
			now,
			bytes.NewReader(bytes.Repeat(
				[]byte{0xb4},
				2*identitySessionNonceBytes,
			)),
			nil,
		)
		arguments, _ := newPostgresOAuthFirstLoginCapturedArguments()
		expectPostgresOAuthFirstLoginTransactionPrefix(mock)
		expectPostgresOAuthFirstLoginCompletionQuery(
			mock,
			arguments,
			nil,
			&pq.Error{
				Code:    pq.ErrorCode("23505"),
				Message: "canonical_email_conflict",
			},
		)
		mock.ExpectRollback()
		_, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		requirePostgresOAuthFirstLoginError(
			t,
			err,
			http.StatusConflict,
			"oauth_first_login_email_conflict",
		)
		if receipt.SessionID() != "" {
			t.Fatalf("query failure returned receipt: %v", receipt)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("malformed result before commit", func(t *testing.T) {
		coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
			t,
			now,
			bytes.NewReader(bytes.Repeat(
				[]byte{0xb5},
				2*identitySessionNonceBytes,
			)),
			nil,
		)
		arguments, _ := newPostgresOAuthFirstLoginCapturedArguments()
		expectPostgresOAuthFirstLoginTransactionPrefix(mock)
		rows := postgresOAuthFirstLoginCompletionRows(
			command,
			now.Add(defaultIdentityAccessSessionTTL),
			now.Add(defaultIdentityRefreshSessionTTL),
			true,
		)
		rows = sqlmock.NewRows([]string{
			"session_id",
			"principal_id",
			"credential_id",
			"connection_id",
			"token_ref_id",
			"created",
			"organization_id",
			"project_id",
			"provider_name",
			"access_expires_at",
			"refresh_expires_at",
			"completed_at",
		}).AddRow(
			"not-a-uuid",
			postgresOAuthFirstLoginPrincipalID,
			postgresOAuthFirstLoginCredentialID,
			postgresOAuthFirstLoginConnectionID,
			postgresOAuthFirstLoginTokenRefID,
			true,
			command.OrganizationID,
			command.ProjectID,
			command.Provider,
			now.Add(defaultIdentityAccessSessionTTL),
			now.Add(defaultIdentityRefreshSessionTTL),
			command.CompletedAt,
		)
		expectPostgresOAuthFirstLoginCompletionQuery(
			mock,
			arguments,
			rows,
			nil,
		)
		mock.ExpectRollback()
		_, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		requirePostgresOAuthFirstLoginError(
			t,
			err,
			http.StatusServiceUnavailable,
			"oauth_first_login_unavailable",
		)
		if receipt.SessionID() != "" {
			t.Fatalf("malformed row returned receipt: %v", receipt)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})

	t.Run("commit", func(t *testing.T) {
		coordinator, _, mock := newPostgresOAuthFirstLoginTestCoordinator(
			t,
			now,
			bytes.NewReader(bytes.Repeat(
				[]byte{0xb6},
				2*identitySessionNonceBytes,
			)),
			nil,
		)
		arguments, _ := newPostgresOAuthFirstLoginCapturedArguments()
		expectPostgresOAuthFirstLoginTransactionPrefix(mock)
		expectPostgresOAuthFirstLoginCompletionQuery(
			mock,
			arguments,
			postgresOAuthFirstLoginCompletionRows(
				command,
				now.Add(defaultIdentityAccessSessionTTL),
				now.Add(defaultIdentityRefreshSessionTTL),
				true,
			),
			nil,
		)
		mock.ExpectCommit().WillReturnError(errors.New("commit failed"))
		_, receipt, err := coordinator.CompleteOAuthFirstLogin(
			context.Background(),
			command,
		)
		requirePostgresOAuthFirstLoginError(
			t,
			err,
			http.StatusServiceUnavailable,
			"oauth_first_login_unavailable",
		)
		if receipt.SessionID() != "" {
			t.Fatalf("commit failure returned receipt: %v", receipt)
		}
		if err := mock.ExpectationsWereMet(); err != nil {
			t.Fatal(err)
		}
	})
}

func TestPostgresOAuthFirstLoginCompletionRowValidation(t *testing.T) {
	now := time.Date(2026, 7, 23, 13, 0, 0, 0, time.UTC)
	coordinator, _, _ := newPostgresOAuthFirstLoginTestCoordinator(
		t,
		now,
		bytes.NewReader(bytes.Repeat([]byte{0xc1}, 256)),
		nil,
	)
	command := validPostgresOAuthFirstLoginCommand(now)
	material, err := coordinator.prepareMaterial(command)
	if err != nil {
		t.Fatal(err)
	}
	validRow := postgresOAuthFirstLoginCompletionRow{
		sessionID:        postgresOAuthFirstLoginSessionID,
		principalID:      postgresOAuthFirstLoginPrincipalID,
		credentialID:     postgresOAuthFirstLoginCredentialID,
		connectionID:     postgresOAuthFirstLoginConnectionID,
		tokenRefID:       postgresOAuthFirstLoginTokenRefID,
		created:          true,
		organizationID:   command.OrganizationID,
		projectID:        command.ProjectID,
		provider:         command.Provider,
		accessExpiresAt:  material.accessExpiresAt,
		refreshExpiresAt: material.refreshExpiresAt,
		completedAt:      command.CompletedAt,
	}
	if err := coordinator.validateCompletionRow(material, validRow); err != nil {
		t.Fatalf("valid completion row rejected: %v", err)
	}
	for name, mutate := range map[string]func(*postgresOAuthFirstLoginCompletionRow){
		"session UUID": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.sessionID = "invalid"
		},
		"principal UUID": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.principalID = "invalid"
		},
		"credential UUID": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.credentialID = "invalid"
		},
		"connection UUID": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.connectionID = "invalid"
		},
		"token ref UUID": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.tokenRefID = "invalid"
		},
		"organization": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.organizationID = postgresOAuthFirstLoginProjectID
		},
		"project": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.projectID = postgresOAuthFirstLoginOrganizationID
		},
		"provider": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.provider = "github"
		},
		"access expiry": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.accessExpiresAt = row.accessExpiresAt.Add(time.Second)
		},
		"refresh expiry": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.refreshExpiresAt = row.refreshExpiresAt.Add(time.Second)
		},
		"completion zero": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.completedAt = time.Time{}
		},
		"completion before accepted window": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.completedAt = command.CompletedAt.Add(
				-maxPostgresOAuthFirstLoginCompletionSkew - time.Nanosecond,
			)
		},
		"completion after server clock": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.completedAt = now.Add(
				maxPostgresOAuthFirstLoginCompletionSkew + time.Nanosecond,
			)
		},
		"completion after access expiry": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.completedAt = row.accessExpiresAt
		},
		"refresh not after access": func(row *postgresOAuthFirstLoginCompletionRow) {
			row.refreshExpiresAt = row.accessExpiresAt
		},
	} {
		t.Run(name, func(t *testing.T) {
			row := validRow
			mutate(&row)
			if err := coordinator.validateCompletionRow(material, row); err == nil {
				t.Fatal("invalid completion row was accepted")
			}
		})
	}
	material.accessToken.bearer = ""
	material.refreshToken.bearer = ""
}
