package ashrclone

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func receiptForTest(t *testing.T, previous, status string) ProviderExecutionReceipt {
	t.Helper()
	r, err := CreateProviderExecutionReceipt(ProviderReceiptOptions{Provider: "xjtlu", Model: "gpt-5.6-sol", Endpoint: "https://models.example/v1", InvokedAt: "2026-07-13T01:02:03Z", CompletedAt: "2026-07-13T01:02:04Z", RequestBinding: JSONMap{"prompt_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}, ResponseBinding: JSONMap{"finish": "stop", "tokens": 7}, Evidence: []byte("private normalized record"), Capabilities: []string{"text", "stream", "tools", "usage"}, Status: status, GitSHA: "5dd6a898a6771eaf67bf39246f256b579b4d2211", ReleaseCandidate: "round62", RequestID: "provider-request-id", PreviousReceiptSHA256: previous, SafeResponseShape: JSONMap{"finish_reason": "stop", "usage_present": true}})
	if err != nil {
		t.Fatal(err)
	}
	return r
}
func TestProviderReceiptTamperAndFailureSemantics(t *testing.T) {
	r := receiptForTest(t, "", "succeeded")
	if err := VerifyProviderExecutionReceipt(r, nil); err != nil {
		t.Fatal(err)
	}
	r.Model = "tampered"
	if VerifyProviderExecutionReceipt(r, nil) == nil {
		t.Fatal("tamper accepted")
	}
	failed := receiptForTest(t, "", "failed")
	if len(failed.Capabilities) != 0 {
		t.Fatal("failed call claimed capabilities")
	}
}
func TestProviderReceiptStoreChain(t *testing.T) {
	path := filepath.Join(t.TempDir(), "receipts.json")
	s := ProviderExecutionReceiptStore{Path: path}
	a := receiptForTest(t, "", "succeeded")
	if err := s.Append(a); err != nil {
		t.Fatal(err)
	}
	b := receiptForTest(t, a.ReceiptSHA256, "succeeded")
	if err := s.Append(b); err != nil {
		t.Fatal(err)
	}
	if v, err := s.Load(); err != nil || len(v) != 2 {
		t.Fatalf("load %d %v", len(v), err)
	}
	if s.Append(receiptForTest(t, "", "succeeded")) == nil {
		t.Fatal("fork accepted")
	}
	raw, _ := os.ReadFile(path)
	var values []map[string]any
	_ = json.Unmarshal(raw, &values)
	values[0]["model"] = "tampered"
	raw, _ = json.Marshal(values)
	_ = os.WriteFile(path, raw, 0600)
	if _, err := s.Load(); err == nil {
		t.Fatal("tamper accepted")
	}
}
func TestA1ReleaseReceipt(t *testing.T) {
	r := receiptForTest(t, "", "succeeded")
	release, err := BuildA1ReleaseReceipt(r.GitSHA, "round62", "2026-07-13T02:00:00Z", []ProviderExecutionReceipt{r}, map[string][]byte{"postgres_rls": []byte("rls"), "claim_lease_fencing": []byte("fencing"), "restart_persistence": []byte("restart")})
	if err != nil {
		t.Fatal(err)
	}
	if err = VerifyA1ReleaseReceipt(release); err != nil {
		t.Fatal(err)
	}
	release.GitSHA = "0000000000000000000000000000000000000000"
	if VerifyA1ReleaseReceipt(release) == nil {
		t.Fatal("tamper accepted")
	}
}

func TestProviderReceiptCrossLanguageVector(t *testing.T) {
	r, err := CreateProviderExecutionReceipt(ProviderReceiptOptions{Provider: "vector", Model: "模型<&>", Endpoint: "https://models.example/v1/", InvokedAt: "2026-07-13T09:02:03+08:00", CompletedAt: "2026-07-13T01:02:04.999Z", RequestBinding: JSONMap{"文本": "你好<&>", "nested": JSONMap{"z": 2, "a": 1}}, ResponseBinding: JSONMap{"finish": "stop", "tokens": 7}, Evidence: []byte("固定证据"), Capabilities: []string{"usage", "text", "text"}, Status: "succeeded", GitSHA: "5dd6a898a6771eaf67bf39246f256b579b4d2211", ReleaseCandidate: "round62-vector", RequestID: "request-中文", SafeResponseShape: JSONMap{"usage_present": true, "标签": "值<&>"}})
	if err != nil {
		t.Fatal(err)
	}
	if r.ReceiptID != "provider_receipt_42a6dd7d4ea1be5586df" || r.ReceiptSHA256 != "57dbeb922ed053321ca13aad95cff850103948b780f892600b4a2b43d2e2b4b0" {
		t.Fatalf("cross-language vector drift: %s %s", r.ReceiptID, r.ReceiptSHA256)
	}
}
