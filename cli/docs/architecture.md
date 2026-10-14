---
hide:
  - navigation
---

# Architecture

Click the diagram to enlarge it.

```mermaid
flowchart LR
  cli(["platform CLI"])
  browser(["browser"])

  subgraph local["platform-local (k3d)"]
    direction LR
    keycloak["Keycloak<br/><small>Google sign-in</small>"]
    api["Platform API<br/><small>validates the token, writes the request</small>"]
    crds[("CRDs<br/><small>Environment, catalog,<br/>ScmConnection, CloudAccount</small>")]
    subgraph providers["providers"]
      vcluster["local_vcluster"]
      scm["scm_github"]
      aws["aws_account"]
    end
    envs["vcluster env-&lt;name&gt;<br/><small>one per environment</small>"]
  end

  github(["GitHub"])
  awscloud(["AWS"])

  cli -- "HTTP + token" --> api
  cli -. login .-> browser -.-> keycloak
  api --> crds
  crds <-- watch --> vcluster & scm & aws
  vcluster --> envs
  scm --> github
  aws --> awscloud
  cli -- kubeconfig --> envs
```

The CLI only talks to the **Platform API**, which writes each request as a Kubernetes resource (**CRD**). The **providers** watch those resources and do the work: create the vcluster, talk to GitHub or AWS. Everything runs inside `platform-local`, installed by `init`; **there is no process to keep open on the host**.
