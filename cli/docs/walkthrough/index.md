# Walkthrough

A walkthrough to demonstrate the `platform` CLI **starting from scratch**: no cluster, no config and no CLI installed. Follow it in order, one step per page: each step builds on the previous ones. To look up a command, a flag or a status, use the [reference](../reference/index.md).

!!! info "Last run"
    Run end to end on 2026-10-10; steps 8 to 11 were redone with the `local_vcluster` provider (#183) and step 14 (#190) on `platform-local`, on the same day. Step 18 (#199) was run on 2026-10-11, with the `wasp-foundry-platform` App created and installed in the `wasp-foundry` org.

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

- [0. From scratch](setup/00-from-scratch.md)
- [1. Prerequisites](setup/01-prerequisites.md)
- [2. Install the CLI](setup/02-install.md)
- [3. Google credentials](setup/03-google-credentials.md)
- [4. Start the control plane](setup/04-control-plane.md)

**Login**

- [5. Without login, the API refuses](login/05-refused.md)
- [6. Sign in](login/06-sign-in.md)
- [7. Who am I](login/07-whoami.md)

**Environments**

- [8. Create an environment](environments/08-create.md)
- [9. The provider inside](environments/09-provider.md)
- [10.1 Write the kubeconfig](environments/10-1-kubeconfig.md)
- [10.2 Use the cluster](environments/10-2-cluster.md)
- [10.3 Admin kubeconfig](environments/10-3-admin.md)
- [11. A second environment, in parallel](environments/11-second.md)
- [12. Audit trail](environments/12-audit-trail.md)

**Catalog**

- [13.1 Create the team and the hierarchy](catalog/13-1-hierarchy.md)
- [13.2 Query](catalog/13-2-query.md)
- [13.3 A domain with dependents stays](catalog/13-3-dependents.md)
- [13.4 Underneath, they are CRDs](catalog/13-4-crds.md)
- [13.5 Clean up, in reverse order](catalog/13-5-cleanup.md)
- [14.1 Import from Backstage](catalog/14-1-plan.md)
- [14.2 Run it again](catalog/14-2-rerun.md)
- [14.3 Broken reference](catalog/14-3-broken-reference.md)

**Teams**

- [15.1 Join the team](teams/15-1-join.md)
- [15.2 Renew the token](teams/15-2-token.md)
- [15.3 Share an environment](teams/15-3-share.md)
- [15.4 Unshare](teams/15-4-unshare.md)
- [15.5 A team in use is not deleted](teams/15-5-in-use.md)

**Component templates**

- [16.1 List and get](templates/16-1-list.md)
- [16.2 Render](templates/16-2-render.md)
- [16.3 Another template as the default](templates/16-3-new-default.md)
- [16.4 The default does not leave alone](templates/16-4-default-stays.md)
- [16.5 Another takes over, then it leaves](templates/16-5-handover.md)
- [16.6 Backstage template](templates/16-6-backstage-import.md)

**Cloud accounts**

- [17.1 Base credential](cloud-accounts/17-1-base-credential.md)
- [17.2 Register the account](cloud-accounts/17-2-register.md)
- [17.3 Apply the trust policy](cloud-accounts/17-3-trust-policy.md)
- [17.4 Verify](cloud-accounts/17-4-verify.md)
- [17.5 ExternalId and removal](cloud-accounts/17-5-remove.md)

**GitHub connection**

- [18.1 Create the App](scm-connection/18-1-create-app.md)
- [18.2 Install on the org](scm-connection/18-2-install.md)
- [18.3 Verify](scm-connection/18-3-verify.md)
- [18.4 The key stays off this machine](scm-connection/18-4-private-key.md)
- [18.5 Remove](scm-connection/18-5-remove.md)

- [19. Clean up and sign out](19-cleanup.md)

Without a browser: [`scripts/demo/cli-smoke`](cli-smoke.md).

## Ideas to make the walkthrough repeatable

??? abstract "Open issues for the walkthrough"

    - **Script `scripts/demo/cli-walkthrough` (#178):** runs the steps in sequence, pauses before each one (Enter to continue) and stops at sign in waiting for the device code. Use it to present and to check before a merge.
    - **Measure (#180):** record the time of each step (as in the table above) to notice when `init` or the provider get slower.
    - **Record (#181):** `asciinema rec` during the walkthrough produces a lightweight terminal video for the README and the deck.
    - **Evolve with the CLI (#182):** each new command (`release create`, `catalog component create`) is added here as a step, with the expected output.
