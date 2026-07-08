package ashrclone

import (
	"encoding/base64"
	"fmt"
	"strings"
	"unicode"
)

type MediaSafetyError struct {
	Path   string
	Reason string
}

func (err MediaSafetyError) Error() string {
	return fmt.Sprintf("media-unsafe request envelope at %s: %s", err.Path, err.Reason)
}

func ValidateMediaSafeEnvelope(value any) error {
	return validateMediaSafe(value, "$", "")
}

func validateMediaSafe(value any, path, key string) error {
	if key != "" && isInlineMediaKey(key) {
		return MediaSafetyError{Path: path, Reason: fmt.Sprintf("field %q can carry inline media bytes", key)}
	}
	switch typed := value.(type) {
	case JSONMap:
		for itemKey, item := range typed {
			if err := validateMediaSafe(item, path+"."+itemKey, itemKey); err != nil {
				return err
			}
		}
	case map[string]any:
		for itemKey, item := range typed {
			if err := validateMediaSafe(item, path+"."+itemKey, itemKey); err != nil {
				return err
			}
		}
	case []any:
		for index, item := range typed {
			if err := validateMediaSafe(item, fmt.Sprintf("%s[%d]", path, index), ""); err != nil {
				return err
			}
		}
	case []JSONMap:
		for index, item := range typed {
			if err := validateMediaSafe(item, fmt.Sprintf("%s[%d]", path, index), ""); err != nil {
				return err
			}
		}
	case string:
		if strings.HasPrefix(strings.ToLower(strings.TrimSpace(typed)), "data:") {
			return MediaSafetyError{Path: path, Reason: "data URLs are not allowed; pass a URL or file path reference"}
		}
		if looksLikeInlineBase64Media(key, typed) {
			return MediaSafetyError{Path: path, Reason: "inline base64 media is not allowed; pass a URL or file path reference"}
		}
	case []byte:
		return MediaSafetyError{Path: path, Reason: "raw byte slices are not allowed; pass a URL or file path reference"}
	}
	return nil
}

func isInlineMediaKey(key string) bool {
	normalized := strings.ToLower(strings.ReplaceAll(key, "-", "_"))
	switch normalized {
	case "raw_payload", "raw_media", "media_bytes", "bytes", "byte_data", "base64", "base64_data", "data_uri", "data_url", "inline_data":
		return true
	default:
		return false
	}
}

func looksLikeInlineBase64Media(key, value string) bool {
	if len(value) < 64 {
		return false
	}
	normalized := strings.ToLower(strings.ReplaceAll(key, "-", "_"))
	if !strings.Contains(normalized, "image") && !strings.Contains(normalized, "audio") && !strings.Contains(normalized, "video") && !strings.Contains(normalized, "media") {
		return false
	}
	trimmed := strings.TrimSpace(value)
	if len(trimmed)%4 != 0 {
		return false
	}
	for _, r := range trimmed {
		if unicode.IsLetter(r) || unicode.IsDigit(r) || r == '+' || r == '/' || r == '=' || r == '-' || r == '_' {
			continue
		}
		return false
	}
	_, err := base64.StdEncoding.DecodeString(strings.ReplaceAll(strings.ReplaceAll(trimmed, "-", "+"), "_", "/"))
	return err == nil
}
