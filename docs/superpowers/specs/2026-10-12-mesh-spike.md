# Mesh in Environment vclusters — Spike

Issue [#338](https://github.com/smsilva/wasp-idp/issues/338), sub-issue da [#295](https://github.com/smsilva/wasp-idp/issues/295) (fase 3 do Workload Instance, ADR 0033). Decisão registrada no [ADR 0035](../../adr/0035-istio-sidecar-per-environment-vcluster-gamma-routes.md). Rodado em 2026-10-12 no k3d `platform-local` (k3s v1.31.5), vcluster chart 0.37.2.

## Pergunta

O roteamento da fase 3 é east-west: `productpage` chama `reviews` e o header decide se a chamada vai para `reviews` ou `reviews-pr-42`. Um Gateway north-south não vê essa chamada, então a peça precisa ser um mesh que implemente GAMMA (`HTTPRoute` com `parentRef` num Service). Qual mesh, e instalado onde?

## Cenário

Em cada vcluster: Gateway API v1.3.0 (CRDs standard), namespace `apps` com injeção, as duas instâncias no formato que o provider `workload` gera (Deployment + Service por instância, seletor com `app.kubernetes.io/name` e `/instance`; um `http-echo` que responde o nome da instância), um pod cliente com `curl` e este `HTTPRoute`:

```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata: {name: reviews, namespace: apps}
spec:
  parentRefs: [{group: "", kind: Service, name: reviews, port: 9080}]
  rules:
  - matches: [{headers: [{name: x-sandbox, value: pr-42}]}]
    backendRefs: [{name: reviews-pr-42, port: 9080}]
  - matches: [{headers: [{type: RegularExpression, name: baggage, value: ".*sandbox=pr-42.*"}]}]
    backendRefs: [{name: reviews-pr-42, port: 9080}]
  - backendRefs: [{name: reviews, port: 9080, weight: 90}, {name: reviews-pr-42, port: 9080, weight: 10}]
```

O `parentRef` é o Service `reviews` da instância principal, e os `backendRefs` são os Services das instâncias: o modelo da fase 2 serve sem mudança.

## Resultados

| | Istio 1.30.5 sidecar, `istiod` por vcluster | Linkerd edge-26.10.1, por vcluster | Istio no host (integração do vcluster) |
|---|---|---|---|
| `HTTPRoute` aceito | `istio.io/gateway-controller`, `Accepted`, `ResolvedRefs` | `linkerd.io/policy-controller`, `Accepted`, `ResolvedRefs` | — |
| Header `x-sandbox: pr-42` | 20/20 em `pr-42` | 20/20 em `pr-42` | — |
| Baggage `userid=1,sandbox=pr-42` | 20/20 em `pr-42` | 20/20 em `pr-42` | — |
| Peso 90/10, 200 chamadas | 181/19 | 184/16 | — |
| Instalação do mesh | 30 s (`istio/base` + `istio/istiod`) | 49 s (`linkerd install` + `check`) | — |
| Memória do mesh | `istiod` 42 Mi + ~50 Mi por proxy | control plane ~71 Mi + ~6 Mi por proxy | — |
| Atrito | nenhum | stable só pela Buoyant; `proxyInit.runAsRoot=true` no runtime do k3d; trust anchor e issuer a gerar e renovar quando instalado por Helm | Enterprise; só ambient |

A integração Istio do vcluster ficou fora sem teste: a documentação a marca como Enterprise e diz "works only with Istio in Ambient mode. Sidecar mode is not supported". Ambient já estava descartado na #295: o roteamento L7 exige waypoint e o ztunnel roda por nó do host, compartilhado entre vclusters.

### Onde instalar

- **Pelo chart do vcluster** (`experimental.deploy.vcluster.helm` com os charts em `bundle`, e os CRDs em `manifests`): funciona, `istiod` pronto 49 s depois do `helm install`. Mas os CRDs do Gateway API pesam 650 KB (o de `httproutes` sozinho, 368 KB) e os values chegam a 873 KB; o Secret da release do Helm ficou com 1,1 MB em base64, perto do limite de 1 MiB do objeto. Qualquer chart a mais estoura.
- **Pelo controller, depois do vcluster `Ready`**: o mesmo `helm upgrade --install` contra o kubeconfig do vcluster, com os charts embutidos na imagem como o do vcluster já é. Sem limite de tamanho e com versão do mesh independente da do chart do vcluster.

## Recomendação

Istio sidecar por vcluster, instalado pelo `local_vcluster` depois que o vcluster sobe, e a plataforma escrevendo só `HTTPRoute` GAMMA. Linkerd é mais leve, mas a falta de stable open source e a gestão de certificados pesam mais que ~100 Mi por ambiente; o Istio é o que o deck e o ADR 0008 já usam. Como nada além do `HTTPRoute` é do mesh, trocar depois muda só a instalação.

## Limites do spike

- Memória medida com 3 pods e sem carga; o proxy do Istio cresce com o número de Services do vcluster.
- Gateway API v1.3.0 no teste; a versão a fixar é a suportada pela versão do Istio escolhida (1.30 → Gateway API 1.5, pela matriz do vcluster).
- Não testado: tráfego de fora do vcluster (fora da fase 3, #295) e repasse do baggage numa cadeia de chamadas (#340).
