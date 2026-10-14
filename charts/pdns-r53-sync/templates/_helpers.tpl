{{/*
Expand the name of the chart.
*/}}
{{- define "pdns-r53-sync.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "pdns-r53-sync.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label.
*/}}
{{- define "pdns-r53-sync.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "pdns-r53-sync.labels" -}}
helm.sh/chart: {{ include "pdns-r53-sync.chart" . }}
{{ include "pdns-r53-sync.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "pdns-r53-sync.selectorLabels" -}}
app.kubernetes.io/name: {{ include "pdns-r53-sync.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "pdns-r53-sync.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "pdns-r53-sync.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image tag.
*/}}
{{- define "pdns-r53-sync.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Zone name without the trailing dot.
*/}}
{{- define "pdns-r53-sync.zone" -}}
{{- required "zone is required (e.g. example.com)" .Values.zone | lower | trimSuffix "." }}
{{- end }}

{{/*
Name of the Secret holding POWERADMIN_API_KEY / AWS_* (mounted as files).
*/}}
{{- define "pdns-r53-sync.secretName" -}}
{{- if .Values.secretEnv.existingSecret -}}
{{- .Values.secretEnv.existingSecret -}}
{{- else -}}
{{- printf "%s-env" (include "pdns-r53-sync.fullname" .) -}}
{{- end -}}
{{- end }}

{{/*
Secret env vars as a dict of ENV_NAME -> key in the Secret.
With an existing Secret and no explicit mapping, keys are expected to be named like the env vars.
*/}}
{{- define "pdns-r53-sync.secretKeys" -}}
{{- $keys := dict -}}
{{- if .Values.secretEnv.existingSecret -}}
  {{- if .Values.secretEnv.existingSecretKeys -}}
    {{- $keys = .Values.secretEnv.existingSecretKeys -}}
  {{- else -}}
    {{- $_ := set $keys "POWERADMIN_API_KEY" "POWERADMIN_API_KEY" -}}
    {{- if eq .Values.route53.credentials "secret" -}}
      {{- $_ := set $keys "AWS_ACCESS_KEY_ID" "AWS_ACCESS_KEY_ID" -}}
      {{- $_ := set $keys "AWS_SECRET_ACCESS_KEY" "AWS_SECRET_ACCESS_KEY" -}}
    {{- end -}}
  {{- end -}}
{{- else -}}
  {{- range $name, $value := .Values.secretEnv.values -}}
    {{- if ne (toString $value) "" -}}
      {{- $_ := set $keys $name $name -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- $required := list "POWERADMIN_API_KEY" -}}
{{- if eq .Values.route53.credentials "secret" -}}
  {{- $required = list "POWERADMIN_API_KEY" "AWS_ACCESS_KEY_ID" "AWS_SECRET_ACCESS_KEY" -}}
{{- end -}}
{{- range $required -}}
  {{- if not (hasKey $keys .) -}}
    {{- fail (printf "secret %s is not provided: set secretEnv.existingSecret (preferred) or map it in secretEnv.existingSecretKeys" .) -}}
  {{- end -}}
{{- end -}}
{{- toJson $keys -}}
{{- end }}

{{/*
Whether the chart creates the Secret itself (only without existingSecret).
*/}}
{{- define "pdns-r53-sync.createSecret" -}}
{{- if .Values.secretEnv.existingSecret -}}
false
{{- else -}}
true
{{- end -}}
{{- end }}

{{/*
Filters that are always applied, whatever the values say.
*/}}
{{- define "pdns-r53-sync.rejectTypes" -}}
{{- $types := prepend .Values.filters.extraRejectTypes "NS" -}}
{{- if .Values.filters.ignoreRoute53Aliases -}}
{{- $types = append $types "Route53Provider/ALIAS" -}}
{{- end -}}
{{- toJson (uniq $types) -}}
{{- end }}

{{/*
Names left alone on both sides: user patterns plus ACM DNS validation records (_<32 hex>[.name]).
*/}}
{{- define "pdns-r53-sync.rejectNames" -}}
{{- $names := .Values.filters.rejectNames -}}
{{- if .Values.filters.ignoreAcmValidation -}}
{{- $names = append $names "/^_[0-9a-f]{32}(\\.|$)/" -}}
{{- end -}}
{{- toJson (uniq $names) -}}
{{- end }}

{{- define "pdns-r53-sync.rejectNetworks" -}}
{{- $base := list "0.0.0.0/8" "10.0.0.0/8" "100.64.0.0/10" "127.0.0.0/8" "169.254.0.0/16" "172.16.0.0/12" "192.168.0.0/16" "::1/128" "fc00::/7" "fe80::/10" -}}
{{- toJson (uniq (concat $base .Values.filters.extraRejectNetworks)) -}}
{{- end }}
