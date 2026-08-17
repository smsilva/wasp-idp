{{- define "eks.fullClusterName" -}}
{{- if not .Values.clusterId -}}
{{- fail "clusterId is empty — generate it once and pass --set clusterId=<id> (see scripts/provision-eks)" -}}
{{- end -}}
{{- printf "%s-%s" .Values.clusterName .Values.clusterId -}}
{{- end -}}

{{- /*
Deriva o AWS account id a partir do crossplaneArn (índice 4 de qualquer ARN da conta:
arn:aws:iam::ACCOUNT:user/... ou arn:aws:sts::ACCOUNT:assumed-role/...). Usado para
escopar policies à conta corrente sem hardcode nem novo --set. Fallback "unknown-account"
só ocorre quando crossplaneArn não é um ARN real (ex.: placeholder "unused" em
configure-access/teardown) — nesses fluxos a fase que usa o account NÃO é emitida, então
a sentinela jamais chega ao cluster.
*/ -}}
{{- define "eks.awsAccountId" -}}
{{- $parts := splitList ":" .Values.crossplaneArn -}}
{{- if ge (len $parts) 5 -}}
{{- index $parts 4 -}}
{{- else -}}
unknown-account
{{- end -}}
{{- end -}}

{{- define "eks.commonTags" -}}
{{- range $k, $v := .Values.tags }}
      {{ $k }}: {{ $v | quote }}
{{- end }}
{{- end -}}
