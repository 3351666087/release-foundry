package releasefoundry

import (
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"io"
	"mime"
	"net/http"
	"strings"
	"unicode"
)

const maxTenancyRequestBodyBytes = int64(64 * 1024)

func (server *HTTPServer) handleTenancyRoute(
	writer http.ResponseWriter,
	request *http.Request,
	parts []string,
) {
	setTenancyResponseHeaders(writer)
	requestID := tenancyRequestID(request)
	if tenancyRequestContainsIdentityOverride(request) {
		writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
		return
	}
	session, err := server.trustedIdentityHTTPSession(request)
	if err != nil {
		writeTenancyError(writer, ErrTenancyAuthenticationRequired, requestID)
		return
	}
	if server.tenancy == nil {
		writeTenancyError(writer, ErrTenancyNotFound, requestID)
		return
	}
	actorPrincipalID := session.AccountID

	switch {
	case len(parts) == 2 && parts[0] == "v1" && parts[1] == "organizations":
		switch request.Method {
		case http.MethodGet:
			if !tenancyRequestBodyEmpty(request) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			server.queryTenancy(
				writer,
				request,
				TenancyQuery{
					ActorPrincipalID: actorPrincipalID,
					Operation:        TenancyOperationOrganizationList,
				},
				requestID,
			)
		case http.MethodPost:
			var body struct {
				Slug        string `json:"slug"`
				DisplayName string `json:"display_name"`
			}
			if !decodeTenancyRequestObject(request, &body) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			server.mutateTenancy(
				writer,
				request,
				TenancyMutation{
					ActorPrincipalID: actorPrincipalID,
					Operation:        TenancyOperationOrganizationCreate,
					Payload: map[string]any{
						"slug":         body.Slug,
						"display_name": body.DisplayName,
					},
				},
				requestID,
				http.StatusCreated,
			)
		default:
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodGet, http.MethodPost)
		}
	case len(parts) == 4 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects":
		organizationID := strings.TrimSpace(parts[2])
		switch request.Method {
		case http.MethodGet:
			if !tenancyRequestBodyEmpty(request) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			server.queryTenancy(
				writer,
				request,
				TenancyQuery{
					ActorPrincipalID: actorPrincipalID,
					Operation:        TenancyOperationProjectList,
					OrganizationID:   organizationID,
				},
				requestID,
			)
		case http.MethodPost:
			var body struct {
				Slug        string `json:"slug"`
				DisplayName string `json:"display_name"`
			}
			if !decodeTenancyRequestObject(request, &body) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			server.mutateTenancy(
				writer,
				request,
				TenancyMutation{
					ActorPrincipalID: actorPrincipalID,
					Operation:        TenancyOperationProjectCreate,
					OrganizationID:   organizationID,
					Payload: map[string]any{
						"slug":         body.Slug,
						"display_name": body.DisplayName,
					},
				},
				requestID,
				http.StatusCreated,
			)
		default:
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodGet, http.MethodPost)
		}
	case len(parts) == 5 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects":
		if request.Method != http.MethodPatch {
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodPatch)
			return
		}
		var body struct {
			Slug        *string `json:"slug"`
			DisplayName *string `json:"display_name"`
		}
		if !decodeTenancyRequestObject(request, &body) ||
			(body.Slug == nil && body.DisplayName == nil) {
			writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
			return
		}
		payload := make(map[string]any, 2)
		if body.Slug != nil {
			payload["slug"] = *body.Slug
		}
		if body.DisplayName != nil {
			payload["display_name"] = *body.DisplayName
		}
		server.mutateTenancy(
			writer,
			request,
			TenancyMutation{
				ActorPrincipalID: actorPrincipalID,
				Operation:        TenancyOperationProjectUpdate,
				OrganizationID:   strings.TrimSpace(parts[2]),
				ProjectID:        strings.TrimSpace(parts[4]),
				Payload:          payload,
			},
			requestID,
			http.StatusOK,
		)
	case len(parts) == 6 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects" &&
		(parts[5] == "archive" || parts[5] == "restore"):
		if request.Method != http.MethodPost {
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodPost)
			return
		}
		if !decodeTenancyRequestObject(request, &struct{}{}) {
			writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
			return
		}
		operation := TenancyOperationProjectArchive
		if parts[5] == "restore" {
			operation = TenancyOperationProjectRestore
		}
		server.mutateTenancy(
			writer,
			request,
			TenancyMutation{
				ActorPrincipalID: actorPrincipalID,
				Operation:        operation,
				OrganizationID:   strings.TrimSpace(parts[2]),
				ProjectID:        strings.TrimSpace(parts[4]),
				Payload:          map[string]any{},
			},
			requestID,
			http.StatusOK,
		)
	case len(parts) == 6 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects" && parts[5] == "environments":
		organizationID := strings.TrimSpace(parts[2])
		projectID := strings.TrimSpace(parts[4])
		switch request.Method {
		case http.MethodGet:
			if !tenancyRequestBodyEmpty(request) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			server.queryTenancy(
				writer,
				request,
				TenancyQuery{
					ActorPrincipalID: actorPrincipalID,
					Operation:        TenancyOperationEnvironmentList,
					OrganizationID:   organizationID,
					ProjectID:        projectID,
				},
				requestID,
			)
		case http.MethodPost:
			var body struct {
				Name string `json:"name"`
				Kind string `json:"kind"`
			}
			if !decodeTenancyRequestObject(request, &body) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			server.mutateTenancy(
				writer,
				request,
				TenancyMutation{
					ActorPrincipalID: actorPrincipalID,
					Operation:        TenancyOperationEnvironmentCreate,
					OrganizationID:   organizationID,
					ProjectID:        projectID,
					Payload: map[string]any{
						"name": body.Name,
						"kind": body.Kind,
					},
				},
				requestID,
				http.StatusCreated,
			)
		default:
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodGet, http.MethodPost)
		}
	case len(parts) == 8 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects" && parts[5] == "environments" &&
		(parts[7] == "disable" || parts[7] == "enable"):
		if request.Method != http.MethodPost {
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodPost)
			return
		}
		if !decodeTenancyRequestObject(request, &struct{}{}) {
			writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
			return
		}
		operation := TenancyOperationEnvironmentDisable
		if parts[7] == "enable" {
			operation = TenancyOperationEnvironmentEnable
		}
		server.mutateTenancy(
			writer,
			request,
			TenancyMutation{
				ActorPrincipalID: actorPrincipalID,
				Operation:        operation,
				OrganizationID:   strings.TrimSpace(parts[2]),
				ProjectID:        strings.TrimSpace(parts[4]),
				EnvironmentID:    strings.TrimSpace(parts[6]),
				Payload:          map[string]any{},
			},
			requestID,
			http.StatusOK,
		)
	case len(parts) == 6 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects" && parts[5] == "memberships":
		if request.Method != http.MethodGet {
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodGet)
			return
		}
		if !tenancyRequestBodyEmpty(request) {
			writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
			return
		}
		server.queryTenancy(
			writer,
			request,
			TenancyQuery{
				ActorPrincipalID: actorPrincipalID,
				Operation:        TenancyOperationProjectMembershipList,
				OrganizationID:   strings.TrimSpace(parts[2]),
				ProjectID:        strings.TrimSpace(parts[4]),
			},
			requestID,
		)
	case len(parts) == 7 && parts[0] == "v1" && parts[1] == "organizations" &&
		parts[3] == "projects" && parts[5] == "memberships":
		mutation := TenancyMutation{
			ActorPrincipalID: actorPrincipalID,
			OrganizationID:   strings.TrimSpace(parts[2]),
			ProjectID:        strings.TrimSpace(parts[4]),
			TargetAccountID:  strings.TrimSpace(parts[6]),
		}
		switch request.Method {
		case http.MethodPut:
			var body struct {
				Role string `json:"role"`
			}
			if !decodeTenancyRequestObject(request, &body) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			mutation.Operation = TenancyOperationProjectMembershipSet
			mutation.Payload = map[string]any{"role": body.Role}
		case http.MethodDelete:
			if !decodeTenancyRequestObject(request, &struct{}{}) {
				writeTenancyError(writer, ErrTenancyInvalidRequest, requestID)
				return
			}
			mutation.Operation = TenancyOperationProjectMembershipRevoke
			mutation.Payload = map[string]any{}
		default:
			writeTenancyMethodNotAllowed(writer, requestID, http.MethodPut, http.MethodDelete)
			return
		}
		server.mutateTenancy(writer, request, mutation, requestID, http.StatusOK)
	default:
		writeTenancyError(writer, ErrTenancyNotFound, requestID)
	}
}

func (server *HTTPServer) queryTenancy(
	writer http.ResponseWriter,
	request *http.Request,
	query TenancyQuery,
	requestID string,
) {
	result, err := server.tenancy.QueryTenancy(request.Context(), query)
	if err != nil {
		writeTenancyError(writer, err, requestID)
		return
	}
	writeJSON(writer, http.StatusOK, result)
}

func (server *HTTPServer) mutateTenancy(
	writer http.ResponseWriter,
	request *http.Request,
	mutation TenancyMutation,
	requestID string,
	status int,
) {
	idempotencyValues := request.Header.Values("Idempotency-Key")
	if len(idempotencyValues) != 1 {
		writeTenancyError(writer, ErrTenancyInvalidIdempotencyKey, requestID)
		return
	}
	mutation.IdempotencyKey = idempotencyValues[0]
	mutation.RequestID = requestID
	mutation.TraceID = tenancyTraceID(request)
	result, err := server.tenancy.MutateTenancy(request.Context(), mutation)
	if err != nil {
		writeTenancyError(writer, err, requestID)
		return
	}
	writeJSON(writer, status, TenancyMutationEnvelope{
		SchemaVersion:    TenancySchemaVersion,
		Result:           result.Result,
		RequestID:        requestID,
		IdempotentReplay: result.IdempotentReplay,
	})
}

func decodeTenancyRequestObject(request *http.Request, target any) bool {
	if request == nil || request.Body == nil {
		return false
	}
	mediaType, _, err := mime.ParseMediaType(request.Header.Get("Content-Type"))
	if err != nil || mediaType != "application/json" {
		return false
	}
	payload, err := io.ReadAll(io.LimitReader(
		request.Body,
		maxTenancyRequestBodyBytes+1,
	))
	if err != nil || int64(len(payload)) > maxTenancyRequestBodyBytes {
		return false
	}
	payload = bytes.TrimSpace(payload)
	if len(payload) < 2 || payload[0] != '{' || payload[len(payload)-1] != '}' {
		return false
	}
	decoder := json.NewDecoder(bytes.NewReader(payload))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return false
	}
	var trailing any
	return decoder.Decode(&trailing) == io.EOF
}

func tenancyRequestBodyEmpty(request *http.Request) bool {
	if request == nil || request.Body == nil {
		return true
	}
	payload, err := io.ReadAll(io.LimitReader(request.Body, 1))
	return err == nil && len(payload) == 0
}

func tenancyRequestContainsIdentityOverride(request *http.Request) bool {
	if request == nil {
		return false
	}
	for name := range request.Header {
		if tenancyIdentityOverrideName(name) {
			return true
		}
	}
	for name := range request.URL.Query() {
		if tenancyIdentityOverrideName(name) {
			return true
		}
	}
	return false
}

func tenancyIdentityOverrideName(name string) bool {
	var normalized strings.Builder
	for _, character := range strings.ToLower(strings.TrimSpace(name)) {
		if unicode.IsLetter(character) || unicode.IsDigit(character) {
			normalized.WriteRune(character)
		}
	}
	value := normalized.String()
	for _, suffix := range []string{
		"actorprincipalid",
		"actorid",
		"accountid",
		"principalid",
		"sessionid",
		"sessiontoken",
		"sessiondigest",
	} {
		if value == suffix || strings.HasSuffix(value, suffix) {
			return true
		}
	}
	return false
}

func tenancyRequestID(request *http.Request) string {
	if request != nil {
		values := request.Header.Values("X-Request-ID")
		if len(values) == 1 {
			value := strings.TrimSpace(values[0])
			if validTenancyCorrelationID(value) {
				return value
			}
		}
	}
	var random [16]byte
	if _, err := rand.Read(random[:]); err == nil {
		return "req_" + hex.EncodeToString(random[:])
	}
	return "req_unavailable"
}

func tenancyTraceID(request *http.Request) string {
	if request == nil {
		return ""
	}
	values := request.Header.Values("X-ReleaseFoundry-Trace-ID")
	if len(values) != 1 {
		return ""
	}
	value := strings.TrimSpace(values[0])
	if !validTenancyCorrelationID(value) {
		return ""
	}
	return value
}

func setTenancyResponseHeaders(writer http.ResponseWriter) {
	writer.Header().Set("Content-Type", "application/json")
	writer.Header().Set("Cache-Control", "no-store")
	writer.Header().Set("Pragma", "no-cache")
	writer.Header().Set("X-Content-Type-Options", "nosniff")
}

func writeTenancyMethodNotAllowed(
	writer http.ResponseWriter,
	requestID string,
	allowed ...string,
) {
	writer.Header().Set("Allow", strings.Join(allowed, ", "))
	status, code, message := tenancyPublicError(ErrTenancyInvalidRequest)
	writeJSON(writer, http.StatusMethodNotAllowed, JSONMap{
		"schema_version": TenancySchemaVersion,
		"code":           code,
		"message":        message,
		"request_id":     requestID,
	})
	_ = status
}

func writeTenancyError(writer http.ResponseWriter, err error, requestID string) {
	status, code, message := tenancyPublicError(err)
	writeJSON(writer, status, JSONMap{
		"schema_version": TenancySchemaVersion,
		"code":           code,
		"message":        message,
		"request_id":     requestID,
	})
}
