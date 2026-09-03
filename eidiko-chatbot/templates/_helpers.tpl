{{/*
Application name
*/}}
{{- define "eidiko-chatbot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}


{{/*
Full application name

Use the release name directly when it already represents
the application name. This prevents names such as:

eidiko-chatbot-eidiko-chatbot
*/}}
{{- define "eidiko-chatbot.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}


{{/*
Common labels
*/}}
{{- define "eidiko-chatbot.labels" -}}
app.kubernetes.io/name: {{ include "eidiko-chatbot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}


{{/*
Selector labels
*/}}
{{- define "eidiko-chatbot.selectorLabels" -}}
app.kubernetes.io/name: {{ include "eidiko-chatbot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
