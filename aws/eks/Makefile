.PHONY: help check up provision access clean

help: ## Lista os targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

check: ## Valida binários e credenciais AWS
	./scripts/check

up: check ## Cria k3d + Crossplane + providers + functions + credenciais AWS
	./scripts/install-crossplane
	./scripts/install-providers
	./scripts/install-functions
	./scripts/configure-aws-creds

provision: ## Provisiona o EKS (7 fases)
	./scripts/provision-eks

access: ## Configura AccessEntry e kubeconfig do EKS
	./scripts/configure-access

clean: ## Remove os MRs e destrói o k3d (DESTRUTIVO — exige CONFIRM=1)
	@if [ "$(CONFIRM)" != "1" ]; then \
	  echo "RECUSADO: 'make clean' destrói o EKS (recursos REAIS na AWS, ~28-30 min p/ recriar)."; \
	  echo "Confirme com: make clean CONFIRM=1   (só quando realmente for descartar o ambiente)"; \
	  echo "Ver CLAUDE.local.md -> 'Ambiente AWS/EKS — NUNCA destruir sem autorização'."; \
	  exit 1; \
	fi
	./scripts/teardown --yes-destroy
