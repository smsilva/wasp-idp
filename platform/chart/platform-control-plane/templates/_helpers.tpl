{{/*
Renders a full image reference, prefixed by the global `registry` when set. Takes a dict with
`registry` (the chart-level .Values.registry) and `image` (one `images.<key>` entry).
Usage: {{ include "platform-control-plane.image" (dict "registry" .Values.registry "image" .Values.images.registryProvider) }}
Named templates re-bind `$`/`.` to whatever was passed to `include`, not to the chart root — hence
passing both pieces explicitly instead of reaching for `.Values` inside the helper.
*/}}
{{- define "platform-control-plane.image" -}}
{{- if .registry -}}
{{ .registry }}/{{ .image.repository }}:{{ .image.tag }}
{{- else -}}
{{ .image.repository }}:{{ .image.tag }}
{{- end -}}
{{- end -}}
