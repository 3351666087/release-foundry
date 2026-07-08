package ashrclone

import "strings"

const Redacted = "[REDACTED]"

var sensitiveExactKeys = map[string]struct{}{
	"api_key":       {},
	"apikey":        {},
	"authorization": {},
	"secret":        {},
	"token":         {},
	"password":      {},
}

var sensitiveKeyParts = []string{"api_key", "apikey", "secret", "token", "password", "authorization", "bearer"}

func RedactSensitive(value any) any {
	switch typed := value.(type) {
	case JSONMap:
		return redactMap(map[string]any(typed))
	case map[string]any:
		return redactMap(typed)
	case []any:
		items := make([]any, 0, len(typed))
		for _, item := range typed {
			items = append(items, RedactSensitive(item))
		}
		return items
	case string:
		if strings.Contains(strings.ToLower(typed), "bearer ") {
			return Redacted
		}
		return typed
	default:
		return typed
	}
}

func redactMap(input map[string]any) map[string]any {
	output := make(map[string]any, len(input))
	for key, value := range input {
		if isSensitiveKey(key) {
			output[key] = Redacted
			continue
		}
		output[key] = RedactSensitive(value)
	}
	return output
}

func isSensitiveKey(key string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(key, "-", "_"))
	if _, ok := sensitiveExactKeys[normalized]; ok {
		return true
	}
	for _, part := range sensitiveKeyParts {
		if strings.Contains(normalized, part) {
			return true
		}
	}
	return false
}
