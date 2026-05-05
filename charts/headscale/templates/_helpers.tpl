{{/*
Expand the name of the chart.
*/}}
{{- define "headscale.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "headscale.fullname" -}}
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
Create chart name and version as used by the chart label.
*/}}
{{- define "headscale.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "headscale.labels" -}}
helm.sh/chart: {{ include "headscale.chart" . }}
{{ include "headscale.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "headscale.selectorLabels" -}}
app.kubernetes.io/name: {{ include "headscale.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Standalone DERP labels
*/}}
{{- define "headscale.derp.labels" -}}
helm.sh/chart: {{ include "headscale.chart" . }}
{{ include "headscale.derp.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "headscale.derp.selectorLabels" -}}
app.kubernetes.io/name: {{ include "headscale.name" . }}-derp
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "headscale.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "headscale.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image tag — defaults to chart appVersion
*/}}
{{- define "headscale.imageTag" -}}
{{- .Values.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Name of the Secret that holds headscale private keys
*/}}
{{- define "headscale.keysSecretName" -}}
{{- if .Values.keys.existingSecret -}}
{{- .Values.keys.existingSecret -}}
{{- else -}}
{{- include "headscale.fullname" . }}-keys
{{- end -}}
{{- end }}
