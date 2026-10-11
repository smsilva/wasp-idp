# Cloud accounts in the Platform API: CloudAccount CRD, assume-role with ExternalId, BYO without approval

**Status:** Aceito (2026-10-11)

## Contexto

Para provisionar `Environment`s e `Resource`s em nuvem de verdade, a plataforma precisa saber **em quais contas pode criar coisas e com qual credencial**. Hoje isso existe só fora da Platform API: `aws/eks/providers/provider-config-wasp-nonprod.yaml` usa um Secret com uma credencial base (`aws-iam-credential` em `crossplane-system`) mais `assumeRoleChain` para a role `crossplane-wasp-nonprod` da conta spoke. Ninguém cadastra isso pela CLI ou pela API.

O nome do conceito é **cloud account**: uma AWS account, uma Azure subscription ou um GCP project. "provider" foi descartado porque já tem dois donos (os providers de capacidade da plataforma, como `platform/providers/local_vcluster`, e os providers do Crossplane), e `target` também, porque `platform init --target local` já usa o nome.

Uma conta chega à plataforma por dois caminhos:

- **BYO (bring your own):** o usuário traz uma conta que já existe.
- **Vending:** a plataforma cria a conta (Account Factory do Control Tower, subscription vending no Azure, project factory no GCP) e a registra.

O ADR 0025 já definiu, para as scm connections, o padrão que este ADR repete: CRD neutro de vendor, handshake validado por condition e segredo atrás de um `SecretStore`.

## Decisão

**Cada conta é um `CloudAccount` neutro de vendor, registrado pelo próprio dono sem aprovação. A posse é provada pelo handshake com ExternalId, e a plataforma acessa a conta assumindo uma role a partir de uma única credencial base, sem guardar segredo por conta.**

- **`CloudAccount` é um CRD do grupo `platform.wasp.silvios.me`**, namespaced em `platform-system` como o `Environment`, porque o `KubeApplyWriter` (`platform/api/src/platform_api/state.py`) opera num namespace. O objeto tem `spec.vendor` e um bloco por vendor (`spec.aws.roleArn`, `spec.aws.externalId`, `spec.aws.regions`).
- **O `ProviderConfig` do Crossplane é implementação:** um controller o gera a partir da `CloudAccount` quando algo for provisionar na conta. Essa geração entra junto com a ligação entre `Environment` e `CloudAccount`, que é tema de outra issue.
- **Níveis de credencial, em ordem de preferência:**
  1. **Federação, sem segredo:** a nuvem confia no issuer OIDC da plataforma. Fica para quando o control plane estiver na nuvem, porque o issuer do k3d local não é público.
  2. **Credencial base mais delegação, o padrão:** a plataforma tem *uma* identidade, e cada conta é só "qual role assumir" (assume-role na AWS, impersonation no GCP). O registro não carrega segredo.
  3. **Chave estática por conta:** só como saída de emergência.
- **A Platform API nunca persiste segredo de conta** no CRD, na projeção ou no journal. A chave estática, quando entrar, usa o `SecretStore` e a redação do journal (`<redacted, sha256:…>`) do ADR 0025.
- **Handshake com ExternalId (AWS):**
  - A API gera um ExternalId único por `CloudAccount` e não o aceita do cliente.
  - O registro devolve a trust policy que o dono precisa aplicar na role: ela confia no principal da credencial base e exige `sts:ExternalId`.
  - Só quem administra a conta consegue aplicar essa policy, e isso prova a posse.
  - Também fecha o *confused deputy*: o usuário A não registra a role da conta do usuário B, porque a role de B não exige o ExternalId gerado para A.
- **Validação pelo controller, em duas chamadas:**
  - `AssumeRole` **com** o ExternalId deve funcionar, e o `GetCallerIdentity` resultante deve estar na conta do `roleArn`.
  - `AssumeRole` **sem** o ExternalId deve **falhar**. Essa segunda chamada é obrigatória: sem a condição de `sts:ExternalId` na trust policy, a AWS aceita o `AssumeRole` com qualquer ExternalId, e a prova de posse não vale.
  - O resultado fica em conditions: `Ready=True` com reason `Verified`, ou `Ready=False` com `TrustNotEstablished`, `ExternalIdNotEnforced` ou `AccountMismatch`.
- **BYO sem aprovação de `platform-admins`:** o controle é o handshake mais o isolamento por dono, sem humano no meio.
- **Dono e acesso:**
  - A API grava o `sub` do token na anotação `platform.wasp.silvios.me/owner`, como no `Environment`.
  - `list`, `get` e `remove` seguem `is_owner_or_admin` (`platform/api/src/platform_api/environments.py`).
  - O mesmo `roleArn` não pode ser registrado duas vezes.
  - Compartilhar a conta com times segue o modelo do ADR 0026 (`spec.sharedWith`) e entra junto com a ligação a `Environment`, que é quando usar a conta passa a significar algo.
- **Credencial base no target local:** o `platform init`, a única parte que fala direto com o cluster, cria o Secret a partir de um profile do `~/.aws`. Nenhum segredo trafega pela Platform API nesta fase.
- **Vending fica para depois:** é um fluxo com passos e fim, então roda como workflow (ADR 0022) e termina no mesmo `CloudAccount`, sem mudar o objeto.

## Consequências

- O cadastro BYO não precisa de humano no meio. A segurança fica no handshake e no isolamento por dono.
- A credencial base é a peça mais sensível do target local: ela consegue assumir toda role que confia nela. A recomendação é um IAM user dedicado, com permissão só para `sts:AssumeRole` e `sts:GetCallerIdentity`.
- Uma credencial base temporária (SSO ou role) expira, e o `platform init` precisa ser refeito.
- Vending, federação, chave estática e outros vendors ficam abertos como evolução, sem mudar o objeto.
- A implementação da primeira fatia (AWS, assume-role, registro, handshake e validação) é a #193.
