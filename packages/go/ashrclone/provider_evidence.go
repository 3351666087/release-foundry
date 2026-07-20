package ashrclone

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const ProviderEvidenceSchemaVersion = "ashr.a1.provider_execution_receipt.v1"
const A1ReleaseReceiptSchemaVersion = "ashr.a1.release_receipt.v1"

var lowerHex64 = regexp.MustCompile(`^[0-9a-f]{64}$`)
var gitHex = regexp.MustCompile(`^[0-9a-f]{7,64}$`)
var providerCapabilities = map[string]bool{"text": true, "image": true, "audio": true, "file": true, "video": true, "stream": true, "tools": true, "usage": true}

type ProviderExecutionReceipt struct {
	ReceiptID             string   `json:"receipt_id"`
	Provider              string   `json:"provider"`
	Model                 string   `json:"model"`
	EndpointSHA256        string   `json:"endpoint_sha256"`
	InvokedAt             string   `json:"invoked_at"`
	CompletedAt           string   `json:"completed_at"`
	RequestBindingSHA256  string   `json:"request_binding_sha256"`
	ResponseBindingSHA256 string   `json:"response_binding_sha256"`
	EvidenceSHA256        string   `json:"evidence_sha256"`
	Capabilities          []string `json:"capabilities"`
	Status                string   `json:"status"`
	GitSHA                string   `json:"git_sha"`
	ReleaseCandidate      string   `json:"release_candidate"`
	RequestIDSHA256       string   `json:"request_id_sha256"`
	PreviousReceiptSHA256 string   `json:"previous_receipt_sha256"`
	SafeResponseShape     JSONMap  `json:"safe_response_shape"`
	SchemaVersion         string   `json:"schema_version"`
	ReceiptSHA256         string   `json:"receipt_sha256"`
}
type ProviderReceiptOptions struct {
	Provider, Model, Endpoint, InvokedAt, CompletedAt, Status, GitSHA, ReleaseCandidate, RequestID, PreviousReceiptSHA256 string
	RequestBinding, ResponseBinding                                                                                       any
	Evidence                                                                                                              []byte
	Capabilities                                                                                                          []string
	SafeResponseShape                                                                                                     JSONMap
}
type A1EvidenceReference struct {
	Name   string `json:"name"`
	SHA256 string `json:"sha256"`
}
type A1ReleaseReceipt struct {
	SchemaVersion          string                `json:"schema_version"`
	GitSHA                 string                `json:"git_sha"`
	ReleaseCandidate       string                `json:"release_candidate"`
	GeneratedAt            string                `json:"generated_at"`
	ProviderReceiptSHA256s []string              `json:"provider_receipt_sha256s"`
	EvidenceRefs           []A1EvidenceReference `json:"evidence_refs"`
	ReleaseReceiptSHA256   string                `json:"release_receipt_sha256"`
}

func canonicalEvidenceJSON(value any) ([]byte, error) {
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(value); err != nil {
		return nil, err
	}
	return bytes.TrimSuffix(buffer.Bytes(), []byte("\n")), nil
}
func evidenceDigest(value any) (string, error) {
	var b []byte
	var err error
	if bytes, ok := value.([]byte); ok {
		b = bytes
	} else if s, ok := value.(string); ok {
		b = []byte(s)
	} else {
		b, err = canonicalEvidenceJSON(value)
		if err != nil {
			return "", err
		}
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:]), nil
}
func utcTimestamp(value string) (string, error) {
	parsed, err := time.Parse(time.RFC3339Nano, value)
	if err != nil {
		return "", errors.New("timestamp must be timezone-aware ISO-8601")
	}
	return parsed.UTC().Truncate(time.Second).Format(time.RFC3339), nil
}
func receiptPayload(r ProviderExecutionReceipt) JSONMap {
	b, _ := json.Marshal(r)
	var m JSONMap
	_ = json.Unmarshal(b, &m)
	delete(m, "receipt_sha256")
	return m
}
func validateHex(value, name string, optional bool) error {
	if optional && value == "" {
		return nil
	}
	if !lowerHex64.MatchString(value) {
		return fmt.Errorf("%s must be lowercase SHA-256 hex", name)
	}
	return nil
}

func CreateProviderExecutionReceipt(o ProviderReceiptOptions) (ProviderExecutionReceipt, error) {
	if strings.TrimSpace(o.Provider) == "" || strings.TrimSpace(o.Model) == "" || !(strings.HasPrefix(o.Endpoint, "http://") || strings.HasPrefix(o.Endpoint, "https://")) {
		return ProviderExecutionReceipt{}, errors.New("provider, model, and HTTP(S) endpoint are required")
	}
	caps := append([]string(nil), o.Capabilities...)
	sort.Strings(caps)
	unique := caps[:0]
	for _, v := range caps {
		if !providerCapabilities[v] {
			return ProviderExecutionReceipt{}, errors.New("unsupported capability")
		}
		if len(unique) == 0 || unique[len(unique)-1] != v {
			unique = append(unique, v)
		}
	}
	caps = unique
	if len(caps) == 0 {
		return ProviderExecutionReceipt{}, errors.New("capabilities required")
	}
	if o.Status != "succeeded" && o.Status != "failed" {
		return ProviderExecutionReceipt{}, errors.New("invalid status")
	}
	if o.Status == "failed" {
		caps = []string{}
	}
	if !gitHex.MatchString(o.GitSHA) {
		return ProviderExecutionReceipt{}, errors.New("invalid git SHA")
	}
	if len(o.Evidence) == 0 {
		return ProviderExecutionReceipt{}, errors.New("evidence required")
	}
	if err := validateHex(o.PreviousReceiptSHA256, "previous_receipt_sha256", true); err != nil {
		return ProviderExecutionReceipt{}, err
	}
	invoked, err := utcTimestamp(o.InvokedAt)
	if err != nil {
		return ProviderExecutionReceipt{}, err
	}
	completed, err := utcTimestamp(o.CompletedAt)
	if err != nil {
		return ProviderExecutionReceipt{}, err
	}
	a, _ := time.Parse(time.RFC3339Nano, invoked)
	b, _ := time.Parse(time.RFC3339Nano, completed)
	if b.Before(a) {
		return ProviderExecutionReceipt{}, errors.New("completed_at precedes invoked_at")
	}
	endpoint, _ := evidenceDigest(strings.TrimSuffix(o.Endpoint, "/"))
	req, err := evidenceDigest(o.RequestBinding)
	if err != nil {
		return ProviderExecutionReceipt{}, err
	}
	resp, err := evidenceDigest(o.ResponseBinding)
	if err != nil {
		return ProviderExecutionReceipt{}, err
	}
	ev, _ := evidenceDigest(o.Evidence)
	requestID := ""
	if o.RequestID != "" {
		requestID, _ = evidenceDigest(o.RequestID)
	}
	shape := o.SafeResponseShape
	if shape == nil {
		shape = JSONMap{}
	}
	r := ProviderExecutionReceipt{"pending", o.Provider, o.Model, endpoint, invoked, completed, req, resp, ev, caps, o.Status, o.GitSHA, strings.TrimSpace(o.ReleaseCandidate), requestID, o.PreviousReceiptSHA256, shape, ProviderEvidenceSchemaVersion, ""}
	seed := receiptPayload(r)
	seed["receipt_id"] = ""
	d, _ := evidenceDigest(seed)
	r.ReceiptID = "provider_receipt_" + d[:20]
	r.ReceiptSHA256, _ = evidenceDigest(receiptPayload(r))
	return r, nil
}
func VerifyProviderExecutionReceipt(r ProviderExecutionReceipt, expectedPrevious *string) error {
	for n, v := range map[string]string{"endpoint_sha256": r.EndpointSHA256, "request_binding_sha256": r.RequestBindingSHA256, "response_binding_sha256": r.ResponseBindingSHA256, "evidence_sha256": r.EvidenceSHA256, "receipt_sha256": r.ReceiptSHA256} {
		if err := validateHex(v, n, false); err != nil {
			return err
		}
	}
	if err := validateHex(r.RequestIDSHA256, "request_id_sha256", true); err != nil {
		return err
	}
	if err := validateHex(r.PreviousReceiptSHA256, "previous_receipt_sha256", true); err != nil {
		return err
	}
	d, err := evidenceDigest(receiptPayload(r))
	if err != nil || r.SchemaVersion != ProviderEvidenceSchemaVersion || d != r.ReceiptSHA256 {
		return errors.New("provider receipt integrity verification failed")
	}
	if expectedPrevious != nil && r.PreviousReceiptSHA256 != *expectedPrevious {
		return errors.New("provider receipt chain mismatch")
	}
	if r.Status != "succeeded" && r.Status != "failed" {
		return errors.New("provider receipt semantics invalid")
	}
	seen := map[string]bool{}
	for _, capability := range r.Capabilities {
		if !providerCapabilities[capability] || seen[capability] {
			return errors.New("provider receipt semantics invalid")
		}
		seen[capability] = true
	}
	if !sort.StringsAreSorted(r.Capabilities) {
		return errors.New("provider receipt semantics invalid")
	}
	if r.Status != "succeeded" && len(r.Capabilities) > 0 {
		return errors.New("failed receipt cannot claim capabilities")
	}
	return nil
}

type ProviderExecutionReceiptStore struct{ Path string }

func (s ProviderExecutionReceiptStore) Load() ([]ProviderExecutionReceipt, error) {
	b, err := os.ReadFile(s.Path)
	if os.IsNotExist(err) {
		return []ProviderExecutionReceipt{}, nil
	}
	if err != nil {
		return nil, err
	}
	var values []ProviderExecutionReceipt
	if json.Unmarshal(b, &values) != nil {
		return nil, errors.New("receipt store must contain an array")
	}
	previous := ""
	for _, v := range values {
		if err := VerifyProviderExecutionReceipt(v, &previous); err != nil {
			return nil, err
		}
		previous = v.ReceiptSHA256
	}
	return values, nil
}
func (s ProviderExecutionReceiptStore) Append(r ProviderExecutionReceipt) error {
	values, err := s.Load()
	if err != nil {
		return err
	}
	previous := ""
	if len(values) > 0 {
		previous = values[len(values)-1].ReceiptSHA256
	}
	if err = VerifyProviderExecutionReceipt(r, &previous); err != nil {
		return err
	}
	values = append(values, r)
	if err = os.MkdirAll(filepath.Dir(s.Path), 0700); err != nil {
		return err
	}
	b, _ := json.MarshalIndent(values, "", "  ")
	tmp, err := os.CreateTemp(filepath.Dir(s.Path), filepath.Base(s.Path)+".*.tmp")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if _, err = tmp.Write(append(b, '\n')); err == nil {
		err = tmp.Sync()
	}
	if closeErr := tmp.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return err
	}
	return os.Rename(name, s.Path)
}
func BuildA1ReleaseReceipt(gitSHA, candidate, generatedAt string, providers []ProviderExecutionReceipt, evidence map[string][]byte) (A1ReleaseReceipt, error) {
	for _, r := range providers {
		if err := VerifyProviderExecutionReceipt(r, nil); err != nil {
			return A1ReleaseReceipt{}, err
		}
	}
	at, err := utcTimestamp(generatedAt)
	if err != nil {
		return A1ReleaseReceipt{}, err
	}
	hashes := []string{}
	for _, r := range providers {
		hashes = append(hashes, r.ReceiptSHA256)
	}
	sort.Strings(hashes)
	names := []string{}
	for n := range evidence {
		names = append(names, n)
	}
	sort.Strings(names)
	refs := []A1EvidenceReference{}
	for _, n := range names {
		d, _ := evidenceDigest(evidence[n])
		refs = append(refs, A1EvidenceReference{n, d})
	}
	r := A1ReleaseReceipt{A1ReleaseReceiptSchemaVersion, gitSHA, candidate, at, hashes, refs, ""}
	m := JSONMap{}
	b, _ := json.Marshal(r)
	_ = json.Unmarshal(b, &m)
	delete(m, "release_receipt_sha256")
	r.ReleaseReceiptSHA256, _ = evidenceDigest(m)
	return r, nil
}
func VerifyA1ReleaseReceipt(r A1ReleaseReceipt) error {
	if err := validateHex(r.ReleaseReceiptSHA256, "release_receipt_sha256", false); err != nil {
		return err
	}
	m := JSONMap{}
	b, _ := json.Marshal(r)
	_ = json.Unmarshal(b, &m)
	delete(m, "release_receipt_sha256")
	d, _ := evidenceDigest(m)
	if r.SchemaVersion != A1ReleaseReceiptSchemaVersion || d != r.ReleaseReceiptSHA256 {
		return errors.New("release receipt integrity verification failed")
	}
	return nil
}
