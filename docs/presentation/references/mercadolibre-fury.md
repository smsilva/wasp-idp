# Mercado Libre Fury

Caso real de IDP que cuida do ciclo de vida do que provisiona. Fonte: <https://www.youtube.com/watch?v=aFJTxKak6sM>. Resumo fornecido pelo usuário em 2026-10-07; conferir no vídeo (e anotar o timestamp) antes de citar detalhe na tela.

- IDP do Mercado Livre: **Fury**.
- A plataforma monitora se um ambiente provisionado **não está sendo usado** e **sugere a exclusão ao owner** do ambiente.

## Uso na apresentação

- Resposta prática ao "puppy for Christmas" (Platform as a Product, p. 16): o recurso não é abandonado depois do clique — a plataforma lembra quem é o dono e pergunta se ainda precisa.
- Depende de ownership no catálogo: só dá para avisar o dono se o catálogo sabe quem ele é.
- Liga com custo (FinOps): ambiente ocioso é custo sem valor. Em um ambiente de plataforma, cada `Environment` é um cluster EKS com custo correndo.
- A plataforma **sugere**, o owner decide: guardrail, não gate.
