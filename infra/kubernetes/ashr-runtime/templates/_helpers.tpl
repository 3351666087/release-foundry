{{- define "ashr.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ashr.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "ashr.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "ashr.componentName" -}}
{{- printf "%s-%s" (include "ashr.fullname" .root) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "ashr.commonLabels" -}}
app.kubernetes.io/name: {{ include "ashr.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: ashr-a1-runtime
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
ashr.io/environment: {{ .Values.environment | quote }}
{{- end -}}

{{- define "ashr.selectorLabels" -}}
app.kubernetes.io/name: {{ include "ashr.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "ashr.supplyChainAnnotations" -}}
ashr.io/source-repository: {{ .Values.supplyChain.sourceRepository | quote }}
ashr.io/source-revision: {{ .Values.supplyChain.sourceRevision | quote }}
ashr.io/source-tree: {{ .Values.supplyChain.sourceTree | quote }}
ashr.io/sbom-uri: {{ .Values.supplyChain.sbom.uri | quote }}
ashr.io/sbom-sha256: {{ .Values.supplyChain.sbom.sha256 | quote }}
ashr.io/provenance-uri: {{ .Values.supplyChain.provenance.uri | quote }}
ashr.io/provenance-sha256: {{ .Values.supplyChain.provenance.sha256 | quote }}
{{- end -}}

{{- define "ashr.image" -}}
{{- printf "%s@%s" .repository .digest -}}
{{- end -}}

{{- define "ashr.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 65532
runAsGroup: 65532
fsGroup: 65532
fsGroupChangePolicy: OnRootMismatch
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "ashr.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  drop:
    - ALL
privileged: false
readOnlyRootFilesystem: true
runAsNonRoot: true
runAsUser: 65532
runAsGroup: 65532
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "ashr.topologySpread" -}}
- maxSkew: 1
  topologyKey: {{ .root.Values.scheduling.topology.zoneKey }}
  whenUnsatisfiable: {{ .root.Values.scheduling.topology.zoneWhenUnsatisfiable }}
  labelSelector:
    matchLabels:
      {{- include "ashr.selectorLabels" . | nindent 6 }}
- maxSkew: 1
  topologyKey: {{ .root.Values.scheduling.topology.hostnameKey }}
  whenUnsatisfiable: {{ .root.Values.scheduling.topology.hostnameWhenUnsatisfiable }}
  labelSelector:
    matchLabels:
      {{- include "ashr.selectorLabels" . | nindent 6 }}
{{- end -}}

{{- define "ashr.validate" -}}
{{- $known := list
  "sha256:d11aa1b5a977de20a601f45500420e543f3be22fbee21b4c19254165a45d77b9"
  "sha256:75973ade13ec20d39b2d175be0b467351a7a5a93e5540580817318f89b38bdfb"
  "sha256:880482f0bcdcec25c5e7fada9aadf2d15824412f4553aceaa73f30885ccc5841"
  "sha256:bc71da90a0577f2f441783c0292e871947f36df46df948c727c1019992632a17"
  "sha256:5b6c85334c7950eb5d9a1290246a06e6d5e590eece41253953df6d57b37d9919" -}}
{{- if not .Values.supplyChain.allowPlaceholderDigests -}}
  {{- range $name, $image := .Values.images -}}
    {{- if has $image.digest $known -}}
      {{- fail (printf "production image %s still uses a documented placeholder digest" $name) -}}
    {{- end -}}
  {{- end -}}
  {{- if eq .Values.supplyChain.sourceRevision "0000000000000000000000000000000000000000" -}}
    {{- fail "production sourceRevision must bind to a real Git commit" -}}
  {{- end -}}
  {{- if eq .Values.supplyChain.sourceTree "0000000000000000000000000000000000000000" -}}
    {{- fail "production sourceTree must bind to a real Git tree" -}}
  {{- end -}}
  {{- if eq .Values.supplyChain.sbom.sha256 "0000000000000000000000000000000000000000000000000000000000000000" -}}
    {{- fail "production sbom.sha256 must bind to generated evidence" -}}
  {{- end -}}
  {{- if eq .Values.supplyChain.provenance.sha256 "0000000000000000000000000000000000000000000000000000000000000000" -}}
    {{- fail "production provenance.sha256 must bind to generated evidence" -}}
  {{- end -}}
{{- end -}}
{{- if and (eq .Values.environment "production") (lt (int .Values.api.replicaCount) 3) -}}
  {{- fail "production api.replicaCount must be at least 3" -}}
{{- end -}}
{{- if and (eq .Values.environment "production") (lt (int .Values.queueWorker.replicaCount) 3) -}}
  {{- fail "production queueWorker.replicaCount must be at least 3" -}}
{{- end -}}
{{- if and (eq .Values.environment "production") (lt (int .Values.identityDelivery.replicaCount) 3) -}}
  {{- fail "production identityDelivery.replicaCount must be at least 3" -}}
{{- end -}}
{{- range $name, $workload := dict "api" .Values.api "queueWorker" .Values.queueWorker "identityDelivery" .Values.identityDelivery -}}
  {{- if ge (int $workload.pdb.minAvailable) (int $workload.replicaCount) -}}
    {{- fail (printf "%s.pdb.minAvailable must be lower than replicaCount" $name) -}}
  {{- end -}}
{{- end -}}
{{- if and (eq .Values.environment "production") (not .Values.networkPolicy.enabled) -}}
  {{- fail "production networkPolicy.enabled must be true" -}}
{{- end -}}
{{- if and (eq .Values.environment "production") (not .Values.queueWorker.verifier.enabled) -}}
  {{- fail "production queueWorker.verifier.enabled must be true" -}}
{{- end -}}
{{- if eq .Values.scheduling.topology.zoneKey .Values.scheduling.topology.hostnameKey -}}
  {{- fail "zone and hostname topology keys must be distinct" -}}
{{- end -}}
{{- end -}}
