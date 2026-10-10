# Backstage catalog

## System model

Fonte: <https://backstage.io/docs/features/software-catalog/system-model#ecosystem-modeling>

- **Component**: peça de software (serviço, site, pipeline de dados); provê e consome APIs e depende de Resources.
- **API**: fronteira entre Components, em formato legível por máquina; public, restricted ou private.
- **Resource**: infraestrutura de que um Component precisa em runtime (banco, fila, bucket).
- **System**: coleção de Components e Resources que expõe uma ou mais APIs públicas, escondendo a implementação dos consumidores.
- **Domain**: agrupa Systems que compartilham terminologia, modelo e propósito de negócio — um bounded context.
- **User / Group**: pessoas e times; todo Component, API, Resource e System tem `owner`.

## Por que o catálogo não guarda versões

Fonte: <https://backstage.io/docs/features/software-catalog/faq/#can-i-represent-versions-of-apis-services-etc-in-the-catalog>

- "We do not recommend trying to represent fine grained versions in the catalog."
- O catálogo guarda "the human concept of a thing": um serviço com várias versões rodando ao mesmo tempo é **um** Component.
- É dado "rarely changing, human curated", mantido pelo dono.
- Versão fina vem de sistemas externos (CI/CD, registry, deploy) e aparece no portal por **plugins**.
- Exceção: major breaking que na prática é uma coisa nova (`customerinfo` → `customerinfo2`), ao custo de resultados duplicados na busca.

Papel na narrativa: é a **ponte** entre o Developer Control Plane e o Integration & Delivery Plane — o catálogo guarda o conceito estável, e o que muda (versão, ambiente) vive em registry, GitOps e orquestrador.

## Como o arquivo entra no catálogo

Fontes: <https://backstage.io/docs/features/software-catalog/life-of-an-entity>, <https://backstage.io/docs/integrations/github/discovery> (lidas em 2026-10-07).

- Locations registradas: "URLs to yaml files that you register using either the Create button or add to your app-config, are both handled by entity providers."
- Discovery no GitHub: "The provider will crawl the GitHub organization or App and register entities matching the configured path." O exemplo de configuração roda a cada 30 minutos (`frequency: { minutes: 30 }`).
- O processing loop reprocessa cada entidade periodicamente: "Every unprocessed entity comes with a timestamp, which tells at what time that the processing loop should next try to process it." A doc não fixa o intervalo.

## Papel na apresentação: como o dev declara a app

O modelo do Backstage é usado para **ensinar o dev a declarar sua aplicação no catálogo** — não como modelo da própria apresentação. A sequência no Developer Control Plane:

1. Dois níveis: negócio (Domain, System) e implementação (Component, API, Resource).
2. Uma entidade por slide, cada uma com exemplo de sistema conhecido.
3. A árvore completa num exemplo conhecido; depois a mesma árvore no catálogo real do repo.
4. Como declarar: `catalog-info.yaml` junto do código, mostrado como quadro estilo IDE por partes (mesmo formato do Score): arquivo inteiro → identidade (`kind`, `type`, `lifecycle`) → `owner` + `system` → `providesApis` → `dependsOn`. Arquivo: `snippets/catalog-info.yaml` (`greeting-api` com suas dependências). Depois, descoberta automática pelo portal.
5. O que **não** se declara ali (versão, ambiente) — ponte para o próximo ato.

## Exemplo conhecido: o catálogo de demonstração do Backstage

Fonte: <https://github.com/backstage/backstage/tree/master/packages/catalog-model/examples> — modela um serviço de streaming de áudio (Spotify, onde o Backstage nasceu).

```
Domain audio
├─ Domain artists   (subdomainOf: audio)
│  └─ System artist-engagement-portal   owner team-a
│     ├─ Component artist-lookup   dependsOn resource:artists-db
│     ├─ Component www-artist      consome artist-lookup
│     └─ Resource artists-db       type database
└─ Domain playback  (subdomainOf: audio)
   ├─ System audio-playback   owner team-c   playback-order, playback-sdk, shuffle-api
   └─ System podcast          owner team-b   podcast-api, queue-proxy
```

## Catálogo real deste repo

Fonte: `idp/catalog/communication/catalog-info.yaml` (Backstage vanilla validado localmente).

```
Domain communication                 owner platform-team
├─ System greeter                    owner team-alpha         greeting-api, greeting-http, greeting-db, greeting-events, greeting-avatars
└─ System notifier                   owner platform-team
```

- Feito a partir das compositions Crossplane de cada aplicação, só para saber do que a app precisa para rodar. Provisionamento (rede, cluster, LB, firewall, add-ons) fica **fora** do catálogo.
- Resources descritos pelo **papel** (banco relacional, fila, tópico, object storage), não pelo serviço de nuvem — é o que permite ligar o catálogo ao Resource Plane ("no catálogo é banco relacional; no Resource Plane é Azure SQL").
