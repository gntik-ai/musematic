{{- define "musematic-control-plane.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "musematic-control-plane.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-control-plane" .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "musematic-control-plane.configName" -}}
{{- printf "%s-config" (include "musematic-control-plane.fullname" .) -}}
{{- end -}}

{{- define "musematic-control-plane.secretName" -}}
{{- printf "%s-secrets" (include "musematic-control-plane.fullname" .) -}}
{{- end -}}

{{- define "musematic-control-plane.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "musematic-control-plane.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{- define "musematic-control-plane.componentLabels" -}}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: musematic
{{- end -}}

{{- define "musematic-control-plane.apiName" -}}
{{- printf "%s-api" (include "musematic-control-plane.fullname" .) -}}
{{- end -}}

{{- define "musematic-control-plane.schedulerName" -}}
{{- printf "%s-scheduler" (include "musematic-control-plane.fullname" .) -}}
{{- end -}}

{{- define "musematic-control-plane.workerName" -}}
{{- printf "%s-worker" (include "musematic-control-plane.fullname" .) -}}
{{- end -}}

{{- define "musematic-control-plane.wsHubName" -}}
{{- printf "%s-ws-hub" (include "musematic-control-plane.fullname" .) -}}
{{- end -}}
