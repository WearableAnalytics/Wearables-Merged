{{- define "importservice.image" -}}
{{- if .Values.image.digest -}}
{{ printf "%s@%s" .Values.image.repository .Values.image.digest }}
{{- else -}}
{{ printf "%s:%s" .Values.image.repository (required "Set image.tag to a built commit SHA, or set image.digest" .Values.image.tag) }}
{{- end -}}
{{- end -}}
