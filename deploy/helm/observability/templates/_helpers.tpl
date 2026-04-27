{{- define "musematic-observability.namespace" -}}
platform-observability
{{- end }}

{{- define "musematic-observability.labels" -}}
app.kubernetes.io/name: musematic-observability
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: musematic
{{- end }}

{{- define "musematic-observability.dashboardLabels" -}}
{{ include "musematic-observability.labels" . }}
grafana_dashboard: "1"
{{- end }}

{{- define "musematic-observability.ruleLabels" -}}
{{ include "musematic-observability.labels" . }}
prometheus: musematic
role: alert-rules
{{- end }}

{{- define "musematic-observability.dataSourceLabels" -}}
{{ include "musematic-observability.labels" . }}
grafana_datasource: "1"
{{- end }}

{{- define "musematic-observability.lokiLabels" -}}
service
bounded_context
level
namespace
pod
container
{{- end }}
