{{/* Common labels */}}
{{- define "musematic-clamav.labels" -}}
app.kubernetes.io/name: clamav
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: dpa-virus-scanner
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "musematic-clamav.selectorLabels" -}}
app.kubernetes.io/name: clamav
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
