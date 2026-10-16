# Shortcuts for working on this repo. `make` with no target lists them.

UV_BIN := $(shell uv tool dir --bin 2>/dev/null)
DOCS_PORT ?= 8000
DECK := $(CURDIR)/docs/presentation

.DEFAULT_GOAL := help
.PHONY: help all cli cli-uninstall mcp mcp-uninstall docs deck presentation slides

help: ## List the targets
	@grep --extended-regexp '^[a-z-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*## "} {printf "  make %-15s %s\n", $$1, $$2}'

all: cli mcp ## Install `platform` and `platform-mcp` from this checkout; `platform init` builds the images itself

cli: ## Put `platform` on the PATH, editable from this checkout
	uv tool install --force --editable "$(CURDIR)/cli"
	@case ":$${PATH}:" in \
	  *":$(UV_BIN):"*) platform --help > /dev/null && echo "✓ platform on the PATH, from $(CURDIR)/cli" ;; \
	  *) echo "$(UV_BIN) is not on the PATH: run 'uv tool update-shell' and open a new shell" ;; \
	esac

cli-uninstall: ## Remove `platform` from the PATH
	uv tool uninstall wasp-platform 2> /dev/null || echo "wasp-platform is not installed"

mcp: ## Put `platform-mcp` (the MCP server, ADR 0027) on the PATH, editable from this checkout
	uv tool install --force --editable "$(CURDIR)/platform/mcp"
	@case ":$${PATH}:" in \
	  *":$(UV_BIN):"*) platform-mcp --help > /dev/null && echo "✓ platform-mcp on the PATH, from $(CURDIR)/platform/mcp" ;; \
	  *) echo "$(UV_BIN) is not on the PATH: run 'uv tool update-shell' and open a new shell" ;; \
	esac

mcp-uninstall: ## Remove `platform-mcp` from the PATH
	uv tool uninstall wasp-platform-mcp

docs: ## Serve the Platform API guide (platform/docs) with live reload and open it in the browser; builds to a temp dir
	uvx --with mkdocs-material mkdocs serve \
	  --config-file "$(CURDIR)/platform/mkdocs.yml" \
	  --dev-addr 127.0.0.1:$(DOCS_PORT) \
	  --open

# The browser drops the #present-1 fragment when xdg-open turns a file:// URL into a path, so it opens a
# launcher page that redirects to the deck instead.
deck: ## Render the IDP presentation and open it in presentation mode on the first slide; F11 for full screen
	cd "$(DECK)" && ./render-outline idp.yaml
	@launcher="$$(mktemp --suffix=.html)"; \
	  printf '<meta http-equiv="refresh" content="0; url=file://%s/idp.html#present-1">\n' "$(DECK)" > "$${launcher}"; \
	  xdg-open "$${launcher}" 2> /dev/null || open "$${launcher}"
	@echo "✓ deck opened in presentation mode: press F11 for full screen, I for the index, S for the presenter window"

presentation: deck ## Alias of make deck

slides: deck ## Alias of make deck
