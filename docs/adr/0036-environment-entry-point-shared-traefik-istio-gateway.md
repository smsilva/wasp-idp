# Environment entry point: shared Traefik, an Istio Gateway per vcluster, `*.localhost`

**Status:** Aceito (2026-10-12)

## Contexto

Um workload implantado num `Environment` só é alcançável dentro do vcluster (`http://<instance>.apps:<port>`): para chegar de fora, o dev precisa de `kubectl port-forward`. O momento Release/Run da jornada do deck (#202) e os provisioners `dns` e `route` do Forager (#324, #358) precisam de uma URL pública por instância.

No `platform-local` não há ingress controller: o Traefik do k3s está desligado (`scripts/cluster-zero/cluster-create`). As portas do host são `9090` (Platform API), `8180` (Keycloak) e `7100`–`7119`, uma por ambiente, ocupadas pelo API server do vcluster. Cada vcluster já tem Istio sidecar e os CRDs do Gateway API (ADR 0035), e a plataforma expressa roteamento só com o Gateway API.

## Decisão

**Um Traefik compartilhado no `platform-local`, na porta `127.0.0.1:7080`, encaminha cada `*.<environment>.localhost` ao `Gateway` do Istio do vcluster daquele ambiente.**

- **No vcluster:** o `local_vcluster` cria o `Gateway` `platform` (classe `istio`) no namespace `istio-ingress`, com o listener `*.<environment>.localhost` e `allowedRoutes` de todos os namespaces. O Istio cria o Deployment e o Service do gateway; a annotation `networking.istio.io/service-type: ClusterIP` evita um LoadBalancer, que o k3s publicaria com um `svclb` por ambiente. O `Environment` só fica `Ready` com o `Gateway` `Programmed`, e `status.ingress` guarda o domínio e a porta.
- **No host:** um `Ingress` da classe `platform` no namespace `env-<name>` manda `*.<environment>.localhost` ao Service do gateway que o vcluster sincroniza (`platform-istio-x-istio-ingress-x-vcluster`). Uma porta só serve todos os ambientes, e o host decide o ambiente.
- **Traefik pelo helm-controller do k3s** (`HelmChart` em `platform/providers/local_vcluster/deploy/traefik.yaml`): roda mesmo com o Traefik embutido desligado, e o `platform init` não exige `helm` na máquina. É um controller de borda do `platform-local`, sem rotas próprias: as rotas da plataforma continuam sendo `HTTPRoute`.
- **Domínio `*.localhost`** (RFC 6761): resolve para o loopback sem DNS nem internet. `localtest.me`, `lvh.me` e `nip.io` dependem de um DNS público de terceiro. O domínio e a porta são opções do `local_vcluster` (`--domain`, `--ingress-port`).

## Consequências

- O `listener` do `Gateway` só aceita os hosts do próprio ambiente: um `HTTPRoute` que declara o host de outro ambiente não recebe tráfego.
- Uma porta nova (`7080`) no load balancer do k3d: um cluster criado antes ganha a porta no próximo `platform init` (`k3d cluster edit --port-add`, que recria o load balancer).
- Ambientes criados antes desta mudança ganham o `Gateway` no próximo ciclo do `local_vcluster`, como aconteceu com o mesh; os criados antes do ADR 0035 recebem os dois.
- `*.localhost` resolve primeiro para `::1` em alguns sistemas, e o k3d escuta só em `127.0.0.1`: os clientes caem para IPv4.
- Só HTTP. TLS na borda fica para quando o alvo for a nuvem, com um domínio real (Route 53, ADR 0010/0011) no lugar de `localhost`.
