{{/* Common labels every Datum-authored chart applies. */}}
{{- define "datum.labels" -}}
app.kubernetes.io/managed-by: flux
app.kubernetes.io/part-of: datum-platform
{{- end -}}
