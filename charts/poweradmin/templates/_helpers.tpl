{{/*
Expand the name of the chart.
*/}}
{{- define "poweradmin.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "poweradmin.fullname" -}}
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
{{- define "poweradmin.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels.
*/}}
{{- define "poweradmin.labels" -}}
helm.sh/chart: {{ include "poweradmin.chart" . }}
{{ include "poweradmin.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels.
*/}}
{{- define "poweradmin.selectorLabels" -}}
app.kubernetes.io/name: {{ include "poweradmin.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "poweradmin.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "poweradmin.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image tag.
*/}}
{{- define "poweradmin.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Name of the Secret used for file-based secret env injection.
*/}}
{{- define "poweradmin.secretName" -}}
{{- if .Values.secretEnv.existingSecret -}}
{{- .Values.secretEnv.existingSecret -}}
{{- else -}}
{{- printf "%s-env" (include "poweradmin.fullname" .) -}}
{{- end -}}
{{- end }}

{{/*
Whether the chart should create a Secret.
*/}}
{{- define "poweradmin.createSecret" -}}
{{- if .Values.secretEnv.existingSecret -}}
false
{{- else -}}
{{- $hasValues := false -}}
{{- range $name, $value := .Values.secretEnv.values }}
  {{- if ne (toString $value) "" -}}
    {{- $hasValues = true -}}
  {{- end -}}
{{- end -}}
{{- if $hasValues }}true{{ else }}false{{ end -}}
{{- end -}}
{{- end }}

{{/*
Whether there is any secret-backed env configuration at all.
*/}}
{{- define "poweradmin.hasSecretEnv" -}}
{{- if eq (include "poweradmin.createSecret" .) "true" -}}
true
{{- else if gt (len .Values.secretEnv.existingSecretKeys) 0 -}}
true
{{- else -}}
false
{{- end -}}
{{- end }}
