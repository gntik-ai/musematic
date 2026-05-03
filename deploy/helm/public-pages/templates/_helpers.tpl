{{- define "musematic-public-pages.labels" -}}
app.kubernetes.io/name: public-pages
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: public-pages
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{- define "musematic-public-pages.selectorLabels" -}}
app.kubernetes.io/name: public-pages
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
