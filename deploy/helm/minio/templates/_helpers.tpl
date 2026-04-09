{{- define "musematic.minio.fullname" -}}
{{- default "musematic-minio" .Values.clusterName -}}
{{- end -}}

{{- define "musematic.minio.namespace" -}}
{{- default "platform-data" .Values.namespace -}}
{{- end -}}

{{- define "musematic.minio.lookupOrDefault" -}}
{{- $secret := (lookup "v1" "Secret" .namespace .name) -}}
{{- if and $secret (hasKey $secret.data .key) -}}
{{- index $secret.data .key | b64dec -}}
{{- else -}}
{{- .default -}}
{{- end -}}
{{- end -}}
