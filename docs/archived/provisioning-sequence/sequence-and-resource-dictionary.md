# Provisioning Sequence And Resource Dictionary

_2026-08-27_


Duas entregas, nenhuma toca AWS.

**Portada da trilha corporativa:** o par que descreve o monólito `environment-eks` — árvore de
dependência por camada em YAML mais um dicionário com um arquivo por recurso (34 arquivos).
Traduzido para inglês (nome, título e corpo) e limpo de toda referência que não pode aparecer em repo
público: o API group virou `platform.example.com` e a atribuição de origem não cita caminho interno.

**Escrita para este repo:** a sequência autoritativa (`00 · accounts` → `08 · provas`) e o dicionário
de 61 recursos, um arquivo cada. Levantada por inventário do código real, não de memória — as três
raízes Terraform, `aws/docs/accounts/` e o plano da Frente D.

**As invariantes que o inventário confirmou** e que agora estão registradas no documento:

- Leitura entre camadas é **sempre data source com filtro de tag**, nunca `terraform_remote_state` —
  o lado que lê sobrevive a troca de backend ou de chave no lado que escreve. O filtro tem de
  devolver exatamente um id, e `generate-tfvars` confere antes.
- A **fronteira de state segue o ciclo de vida, não a conta**: recurso da conta do hub cuja vida é a
  de um spoke mora no state do spoke, via provider aliasado.
- **Attachment cross-account tem dois portões** — RAM organization-wide (camada `03`, one-off) e o
  `..._accepter` explícito do lado do hub (camada `05`).
- **Pod Identity tem ordenação real aqui**, ao contrário do monólito: a association precisa existir
  antes do Helm release que a consome, ou o pod entra em CrashLoop com `AccessDenied`.
- As **duas propagações de TGW não são simétricas** — trocar os argumentos quebra o roteamento em
  silêncio.
- A camada `00` **não é Terraform e não pode ser**. Região fora da lista aprovada da SCP aparece como
  deny explícito no primeiro `Create*` de qualquer camada posterior, e parece bug de código.

**Onde cada camada in-cluster realmente existe** (levantado nesta sessão, registrado em
`aws/CLAUDE.md`): o XR `Environment` está bloqueado e superado — o `README.md` dele ainda diz
"walk skeleton COMPLETE", que é resíduo. As Compositions param no equivalente às fases 72/74; tudo de
76 em diante (sub-zona, ESO, external-dns, LBC, Istio, cert-manager, app de validação) existe só no
chart faseado. `ArgoCDInstance` tem só a etapa 1.

**Duas armadilhas de higiene de repo público:**

- A chave do Jira da trilha corporativa tinha sobrado numa linha versionada deste arquivo. Removida.
  **Continua alcançável pelo histórico do git** — decidido não reescrever, porque chave de projeto
  sozinha não identifica empresa nem cliente. Ela entrou na lista de tokens em `CLAUDE.local.md`.
- Um dos tokens proibidos **é também palavra inglesa comum**, e casa em frase legítima de doc em
  inglês, virando falso positivo eterno na varredura. Reescrever a frase (`walkthrough`, `sequence`).
  Qual token e quais frases: `CLAUDE.local.md`. **Não repetir o token aqui** — este arquivo é
  versionado, e documentar a armadilha citando-a reintroduz o problema.
