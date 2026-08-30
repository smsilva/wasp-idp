# Local values

Um arquivo, `values.tfvars`, gitignored, com os valores de **identidade** das camadas Terraform.
Cada raiz o carrega por um symlink `values.auto.tfvars` — que o Terraform lê sozinho, sem
`-var-file` e sem passo de geração.

```bash
cp values.tfvars.example values.tfvars
$EDITOR values.tfvars
```

Sem ele, `terraform plan` falha em `base_domain` com uma mensagem que diz o que falta. Isso é o
mecanismo, não um efeito colateral: variável sem default é a forma de falhar fechado, e um valor
herdado de outra conta é pior que um erro.

Decisão em [ADR 0014](../../../docs/adr/0014-single-regional-root-composing-hub-and-cell-modules.md);
o formato tfvars substitui o `values.yaml` do [ADR 0013](../../../docs/adr/0013-consolidate-local-values-yaml.md).
