{{/*
Expand the name of the chart.
*/}}
{{- define "morgenruf.name" -}}
{{- .Chart.Name }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "morgenruf.fullname" -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "morgenruf.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{ include "morgenruf.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "morgenruf.selectorLabels" -}}
app.kubernetes.io/name: {{ include "morgenruf.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
