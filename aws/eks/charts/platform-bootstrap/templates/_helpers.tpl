{{/*
Nome base do release, usado em SA/Role/Job. Curto e determinístico.
*/}}
{{- define "platform-bootstrap.name" -}}
{{- printf "platform-bootstrap-%s" .Values.id | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Nome dos XRs Network e Cluster — ambos = spec.id (o XRD deriva external-names dele; e o
id compartilhado é o que casa as subnets do Network com o EKS do Cluster por label).
*/}}
{{- define "platform-bootstrap.networkName" -}}
{{- .Values.id -}}
{{- end -}}

{{- define "platform-bootstrap.clusterName" -}}
{{- .Values.id -}}
{{- end -}}
