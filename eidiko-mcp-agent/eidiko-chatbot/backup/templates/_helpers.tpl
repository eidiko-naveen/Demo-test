{{/*
Application name
*/}}
{{- define "eidiko-chatbot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}


{{/*
Full application name
*/}}
{{- define "eidiko-chatbot.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "eidiko-chatbot.name" .) | trunc 63 | trimSuffix "-" }}
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
