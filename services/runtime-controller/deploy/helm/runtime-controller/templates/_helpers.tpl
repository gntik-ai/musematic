{{- define "runtime-controller.fullname" -}}
{{- printf "%s-%s" .Release.Name "runtime-controller" | trunc 63 | trimSuffix "-" -}}
{{- end -}}
