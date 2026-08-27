# Terraform Layers Ported To The Corporate Track

_2026-08-26_


Árvore `aws/terraform/` levada para lá numa branch própria: 8 módulos de `src/` sem alteração, três
raízes, scripts, testes, mais README, CLAUDE.md e spec de desenho adaptados. Todo vocabulário local
trocado por `PLACEHOLDER-*`; zero account id, zero nome de bucket, zero nome de conta daqui.
Regressão offline verificada **lá**: 43 testes em 10 diretórios, 0 falhas. As duas lacunas (TGW e tags
de LBC) foram deixadas documentadas como ponto de entrada, não implementadas às cegas.
