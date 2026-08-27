# Terraform Layer 1 — Network Foundation

_2026-08-25_


Bucket de state em raiz própria com `prevent_destroy`, desacoplado de qualquer região; uma raiz por
região com state key própria. Reuso do módulo entre regiões provado com um segundo hub em `us-west-2`
sem alterar uma linha de `src/network`. Isolamento verificado: `plan -destroy` de uma região não
alcança a outra nem o bucket.
