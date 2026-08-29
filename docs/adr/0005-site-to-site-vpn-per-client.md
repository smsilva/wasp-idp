# Site-to-Site VPN per client

**Status:** Aceito

## Contexto

Com ingress único pelo hub (ADR 0004) e nenhum concentrador de VPN corporativo a montante nesta
trilha (ver bifurcação de trilhas em `HANDOFF.md`), é preciso decidir como cada cliente externo
conecta ao TGW do hub.

## Decisão

**Site-to-Site VPN por cliente**, terminando no TGW do hub. Um attachment por cliente, o que
permite route table de tenant isolar nas **duas** direções (ida e volta).

## Consequências

O número de attachments cresce linearmente com o número de clientes — dentro do teto de escala do
TGW, não é o gargalo (o teto de CIDR do ADR 0003 aperta primeiro). Cada cliente precisa configurar
o lado dele do túnel; não há concentrador corporativo absorvendo essa complexidade nesta trilha —
essa é exatamente a bifurcação registrada em `HANDOFF.md`: a trilha corporativa (fora deste repo)
assume concentrador a montante, esta não.
