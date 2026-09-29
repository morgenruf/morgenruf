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

{{/*
Image reference. A digest, when set, wins over the tag so a release can be
pinned to the exact scanned and signed image. Otherwise the tag is used, or
the chart's appVersion when the tag is empty.
Call with (dict "image" .Values.image "appVersion" .Chart.AppVersion).
*/}}
{{- define "morgenruf.image" -}}
{{- if .image.digest -}}
{{ .image.repository }}@{{ .image.digest }}
{{- else -}}
{{ .image.repository }}:{{ .image.tag | default .appVersion }}
{{- end -}}
{{- end }}
