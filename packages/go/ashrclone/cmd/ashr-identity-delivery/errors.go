package main

import (
	"errors"
	"log/slog"
)

type identityDeliveryCommandError struct {
	code    string
	message string
	cause   error
}

func newIdentityDeliveryCommandError(
	code string,
	message string,
	cause error,
) error {
	return &identityDeliveryCommandError{
		code: code, message: message, cause: cause,
	}
}

func (err *identityDeliveryCommandError) Error() string {
	if err == nil || err.message == "" {
		return "identity delivery command failed"
	}
	return err.message
}

func (err *identityDeliveryCommandError) Unwrap() error {
	if err == nil {
		return nil
	}
	return err.cause
}

func identityDeliveryCommandErrorCode(err error) string {
	var commandErr *identityDeliveryCommandError
	if errors.As(err, &commandErr) && commandErr.code != "" {
		return commandErr.code
	}
	return "internal_error"
}

func logIdentityDeliveryError(
	logger *slog.Logger,
	event string,
	err error,
) {
	if logger == nil {
		return
	}
	reason := "identity delivery command failed"
	var commandErr *identityDeliveryCommandError
	if errors.As(err, &commandErr) {
		reason = commandErr.Error()
	}
	logger.Error(
		"identity delivery command failed",
		slog.String("event", event),
		slog.String("error_code", identityDeliveryCommandErrorCode(err)),
		slog.String("reason", reason),
	)
}
