{{/*
Nome base do release, usado em SA/Role/Job. Curto e determinístico.
*/}}
{{- define "platform-bootstrap.name" -}}
{{- printf "platform-bootstrap-%s" .Values.network.id | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Nome do XR Network — igual ao spec.id (o XRD deriva external-names a partir dele).
*/}}
{{- define "platform-bootstrap.networkName" -}}
{{- .Values.network.id -}}
{{- end -}}
