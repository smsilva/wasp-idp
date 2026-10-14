---
hide:
  - navigation
---

# Architecture

The **Platform API** is the platform. The CLI and the MCP server are two of its clients: they send the same requests, with the same login, and get the same answers. Only the API decides what a person may do, so an agent never gets more than the person it acts for (ADR 0027).

Click the diagram to enlarge it.

```mermaid
flowchart LR
  cli(["platform CLI"])
  mcp(["platform-mcp<br/><small>AI agents</small>"])

  subgraph local["platform-local (k3d)"]
    direction LR
    keycloak["Keycloak<br/><small>sign-in, teams</small>"]
    api["Platform API<br/><small>token, permission, journal</small>"]
    crds[("CRDs")]
    subgraph inside["providers: inside the cluster"]
      direction TB
      environment["environment<br/><small>local_vcluster</small>"]
      workload["workload"]
      resources["resources<br/><small>forager</small>"]
      registry["registry"]
    end
    envs["vcluster env-&lt;name&gt;<br/><small>one per environment</small>"]
    subgraph outside["providers: outside services"]
      direction TB
      scmbuild["scm, build<br/><small>scm_github</small>"]
      cloud["cloud-account, environment<br/><small>aws_account, crossplane_aws</small>"]
    end
  end

  github(["GitHub"])
  aws(["AWS"])

  cli & mcp -- "HTTP + token" --> api
  cli -. login .-> keycloak
  api --> crds
  crds <-- watch --> inside & outside
  inside --> envs
  scmbuild --> github
  cloud --> aws
```

- **Clients.** The CLI covers the whole platform; the MCP server exposes it as tools for AI agents, read-only unless started with `--allow-writes`. Both use the login of `platform login`.
- **Platform API.** Validates the Keycloak token on every `/v1/*` route, checks the permission (owner, team, `platform-admins`), writes the request as a CRD and records it in the journal, with the person who asked.
- **Providers.** Each one implements a capability: it watches its CRDs, does the work (a vcluster, a GitHub workflow, an AWS account, a database for a workload) and writes the result back as conditions. `platform status` lists each capability and the provider behind it.

Everything runs inside `platform-local`, installed by `platform init`; **there is no process to keep open on the host**. [Under the hood](reference/under-the-hood.md) shows the CRDs, the journal and the ports.
