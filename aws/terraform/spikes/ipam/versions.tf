terraform {
  required_version = ">= 1.15"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # State LOCAL de proposito. Este spike e descartavel e nao participa da sequencia de
  # provisionamento: por o state no bucket remoto deixaria uma key orfa depois do destroy, e a key
  # e o que separa os states de verdade (ver ../../CLAUDE.md, secao "State"). `*.tfstate` ja e
  # gitignored na raiz do repo.
}
