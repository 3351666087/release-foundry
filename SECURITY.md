# Security Policy

ReleaseFoundry handles release evidence, credentials by reference, and
deployment decisions. Please report security issues privately so maintainers
can investigate before details are disclosed.

## Supported Versions

Until stable releases are tagged, security fixes are maintained on the latest
commit of `main` only. Historical fixtures and release candidates are retained
for reproducibility and are not supported deployment versions.

## Reporting a Vulnerability

Use [GitHub Private Vulnerability Reporting](https://github.com/3351666087/release-foundry/security/advisories/new)
to submit a report. Do not open a public issue for a suspected vulnerability.

Include, when available:

- the affected component and commit or version;
- reproduction steps or a minimal proof of concept;
- the expected and observed security boundary;
- likely impact and prerequisites; and
- any suggested remediation.

Do not include live credentials, customer data, or production evidence. Redact
sensitive values and use synthetic samples.

Maintainers will acknowledge the report, validate its scope, and coordinate a
fix and disclosure through the private advisory. Response and remediation time
depend on severity and reproducibility.

## Research Guidelines

Good-faith testing should use systems and data you own or are authorized to
test. Avoid privacy violations, service disruption, destructive actions, and
access beyond what is necessary to demonstrate the issue.
