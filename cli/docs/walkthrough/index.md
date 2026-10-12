# Walkthrough

A walkthrough to demonstrate the `platform` CLI **starting from scratch**: no cluster, no config and no CLI installed. Follow it in order, one step per page: each step builds on the previous ones. To look up a command, a flag or a status, use the [reference](../reference/index.md).

!!! info "Last run"
    Run end to end on 2026-10-10; Environments were redone with the `local_vcluster` provider (#183) and the Backstage import (#190) on `platform-local`, on the same day. GitHub connection (#199) was run on 2026-10-11, with the `wasp-foundry-platform` App created and installed in the `wasp-foundry` org. Components (#279) were run on 2026-10-11 against the same org, creating `wasp-foundry/hello-api`. The golden path from component to `curl` (#360) was run on 2026-10-12 on a `platform-local` created from scratch, with the same App: component, clone, builds pushed to `ghcr-wasp-foundry`, deploy, history, rollback, the plan, a second instance and its route. The component was `hello-api-2` (`hello-api` already existed in the org); the outputs show it as `hello-api`. Two steps still use a `Version` written by `kubectl`: the revision `ResourcesNotSupported` of The history of a workload (the build refuses a Score like it) and the databases, whose app is a `psql` client.

## Preparation

**One terminal** and **one browser** signed in to the Google account that will sign in to the platform. The environment provider runs inside the cluster.

| Step | Time |
|---|---|
| `platform init` from scratch | ~4 min |
| Sign in (device code + Google) | ~1 min, manual |
| Environment ready (vcluster) | ~30 s |
| Whole walkthrough | ~10 min |

Each step shows the command and, right below it, the expected **output**.

## Walkthrough steps

**Setup**

- [From scratch](setup/from-scratch.md)
- [Prerequisites](setup/prerequisites.md)
- [Install the CLI](setup/install.md)
- [Google credentials](setup/google-credentials.md)
- [Start the control plane](setup/control-plane.md)

**Login**

- [Without login, the API refuses](login/refused.md)
- [Sign in](login/sign-in.md)
- [Who am I](login/whoami.md)
- [What the platform can do](login/status.md)

**Environments**

- [Create an environment](environments/create.md)
- [The provider inside](environments/provider.md)
- [Write the kubeconfig](environments/kubeconfig.md)
- [Use the cluster](environments/cluster.md)
- [Admin kubeconfig](environments/admin.md)
- [A second environment, in parallel](environments/second.md)
- [Audit trail](environments/audit-trail.md)

**Catalog**

- [Create the team and the hierarchy](catalog/hierarchy.md)
- [Query](catalog/query.md)
- [A domain with dependents stays](catalog/dependents.md)
- [Underneath, they are CRDs](catalog/crds.md)
- [Clean up, in reverse order](catalog/cleanup.md)
- [Import from Backstage](catalog/plan.md)
- [Run it again](catalog/rerun.md)
- [Broken reference](catalog/broken-reference.md)

**Teams**

- [Join the team](teams/join.md)
- [Renew the token](teams/token.md)
- [Share an environment](teams/share.md)
- [Unshare](teams/unshare.md)
- [A team in use is not deleted](teams/in-use.md)

**Component templates**

- [List and get](templates/list.md)
- [Render](templates/render.md)
- [Another template as the default](templates/new-default.md)
- [The default does not leave alone](templates/default-stays.md)
- [Another takes over, then it leaves](templates/handover.md)
- [Backstage template](templates/backstage-import.md)

**Cloud accounts**

- [Base credential](cloud-accounts/base-credential.md)
- [Register the account](cloud-accounts/register.md)
- [Apply the trust policy](cloud-accounts/trust-policy.md)
- [Verify](cloud-accounts/verify.md)
- [ExternalId and removal](cloud-accounts/remove.md)

**GitHub connection**

- [Create the App](scm-connection/create-app.md)
- [Install on the org](scm-connection/install.md)
- [Verify](scm-connection/verify.md)
- [The key stays off this machine](scm-connection/private-key.md)

**Components**

- [Create a component](components/create.md)
- [The component in the catalog](components/list.md)
- [What is refused before GitHub](components/refused.md)

**Builds**

- [Build a branch](builds/create.md)
- [The versions of a component](builds/list.md)
- [What a build refuses](builds/refused.md)

**Workloads**

- [Validate a spec before the build](workloads/validate.md)
- [The spec of a version](workloads/spec.md)
- [Deploy a version to an environment](workloads/deploy.md)
- [The history of a workload](workloads/history.md)
- [Roll back and remove](workloads/rollback.md)
- [The plan of an environment](workloads/apply.md)
- [A database for a workload](workloads/resources.md)
- [A database in the shared instance](workloads/compose.md)
- [A database that already exists](workloads/bind.md)
- [Another instance of the same component](workloads/instances.md)

- [Remove the GitHub connection](scm-connection/remove.md)
- [Clean up and sign out](cleanup.md)

Without a browser: [`scripts/demo/cli-smoke`](cli-smoke.md).

## Ideas to make the walkthrough repeatable

??? abstract "Open issues for the walkthrough"

    - **Script `scripts/demo/cli-walkthrough` (#178):** runs the steps in sequence, pauses before each one (Enter to continue) and stops at sign in waiting for the device code. Use it to present and to check before a merge.
    - **Measure (#180):** record the time of each step (as in the table above) to notice when `init` or the provider get slower.
    - **Record (#181):** `asciinema rec` during the walkthrough produces a lightweight terminal video for the README and the deck.
    - **Evolve with the CLI (#182):** each new command (`release create`, `catalog component create`) is added here as a step, with the expected output.
