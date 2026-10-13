# Shortcuts for working on this repo. `make` with no target lists them.

UV_BIN := $(shell uv tool dir --bin 2>/dev/null)

.DEFAULT_GOAL := help
.PHONY: help cli cli-uninstall mcp mcp-uninstall

help: ## List the targets
	@grep --extended-regexp '^[a-z-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*## "} {printf "  make %-15s %s\n", $$1, $$2}'

cli: ## Put `platform` on the PATH, editable from this checkout
	uv tool install --force --editable "$(CURDIR)/cli"
	@case ":$${PATH}:" in \
	  *":$(UV_BIN):"*) platform --help > /dev/null && echo "✓ platform on the PATH, from $(CURDIR)/cli" ;; \
	  *) echo "$(UV_BIN) is not on the PATH: run 'uv tool update-shell' and open a new shell" ;; \
	esac

cli-uninstall: ## Remove `platform` from the PATH
	uv tool uninstall wasp-platform

mcp: ## Put `platform-mcp` (the MCP server, ADR 0027) on the PATH, editable from this checkout
	uv tool install --force --editable "$(CURDIR)/platform/mcp"
	@case ":$${PATH}:" in \
	  *":$(UV_BIN):"*) platform-mcp --help > /dev/null && echo "✓ platform-mcp on the PATH, from $(CURDIR)/platform/mcp" ;; \
	  *) echo "$(UV_BIN) is not on the PATH: run 'uv tool update-shell' and open a new shell" ;; \
	esac

mcp-uninstall: ## Remove `platform-mcp` from the PATH
	uv tool uninstall wasp-platform-mcp
