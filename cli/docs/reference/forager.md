---
# The diagrams need the width of the table of contents.
hide:
  - toc
---

# The Forager

A deploy runs two translations of the same Score. The **Forager** turns the `resources` block into `ResourceRequest`s and provisions each one. The **workload** provider turns the `containers` block into a Deployment, but only after the resources are ready, since the app's variables (`${resources.db.host}`) come from their outputs.

!!! note "One question per resource"
    The Forager never applies the workload. It answers one question: *where does the `db` of this app come from, in this environment?* The answer is a `ResourceRequest` with the mode the binding policy chose, the connection values (`outputs`) and a reference to the Secret with the password. Design: [`docs/superpowers/specs/2026-10-11-forager-design.md`](https://github.com/smsilva/wasp-idp/blob/main/docs/superpowers/specs/2026-10-11-forager-design.md), ADR 0022, 0031 and 0033.

## A deploy, end to end

<figure class="forager-figure" markdown="0">
<div class="forager-scroll">
<svg viewBox="0 0 1100 660" role="img" aria-label="A deploy: the API writes the WorkloadRevision; the Forager reads the resources of the Score and the BindingPolicy, creates the ResourceRequest and provisions the database (in shared-pg on the host, or in the vcluster); the workload provider waits for the ResourceRequest to be Ready and applies the Deployment in the vcluster with its outputs.">
<defs>
<marker id="fg-arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>
<marker id="fg-arr-hot" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="head hot" d="M0,0 L10,5 L0,10 z"/></marker>
</defs>
<text class="cap" x="20" y="22">inputs</text>
<rect class="box" x="20" y="40" width="220" height="56" rx="6"/>
<text class="m" x="34" y="64">platform workload deploy</text>
<text class="s" x="34" y="83">a person or CI</text>
<rect class="box" x="20" y="170" width="220" height="150" rx="6"/>
<text class="t" x="34" y="194">Version 0.5.0 · Score</text>
<text class="m" x="34" y="218">resources:</text>
<text class="m" x="46" y="234">db: {type: postgres}</text>
<text class="m dim" x="34" y="258">containers.app.variables:</text>
<text class="m dim" x="46" y="274">PGHOST: ${resources.db.host}</text>
<text class="m dim" x="46" y="290">PGPASSWORD: ${…password}</text>
<text class="s" x="34" y="310">Version.spec.appSpec</text>
<rect class="box" x="20" y="380" width="220" height="110" rx="6"/>
<text class="t" x="34" y="404">BindingPolicy</text>
<text class="m" x="34" y="428">1 env-demo</text>
<text class="m dim" x="46" y="444">postgres → compose</text>
<text class="m" x="34" y="464">2 platform-default</text>
<text class="m dim" x="46" y="480">postgres → provision</text>
<text class="cap" x="340" y="22">control plane · platform-system</text>
<rect class="box" x="340" y="40" width="230" height="56" rx="6"/>
<text class="t" x="354" y="64">Platform API</text>
<text class="s" x="354" y="83">validates, writes, journals</text>
<rect class="box" x="340" y="150" width="230" height="56" rx="6"/>
<text class="t" x="354" y="174">WorkloadRevision</text>
<text class="s" x="354" y="193">rev 10 · deploy 0.5.0 · open</text>
<rect class="box hot" x="340" y="262" width="230" height="84" rx="6"/>
<text class="t" x="354" y="287">Forager</text>
<text class="s" x="354" y="306">Score resources → ResourceRequest</text>
<text class="s" x="354" y="324">picks the mode, provisions</text>
<rect class="box" x="340" y="404" width="230" height="90" rx="6"/>
<text class="t" x="354" y="428">ResourceRequest</text>
<text class="m" x="354" y="448">demo.hello-api.db</text>
<text class="s" x="354" y="467">mode compose · Ready</text>
<text class="s" x="354" y="484">outputs · secretRef</text>
<rect class="box" x="340" y="556" width="230" height="64" rx="6"/>
<text class="t" x="354" y="580">workload provider</text>
<text class="s" x="354" y="599">Score containers → Deployment</text>
<rect class="frame" x="650" y="30" width="430" height="190" rx="8"/>
<text class="cap" x="666" y="52">host · namespace platform-resources</text>
<rect class="box" x="680" y="70" width="180" height="120" rx="6"/>
<text class="t" x="694" y="96">shared-pg</text>
<text class="s" x="694" y="116">role + database</text>
<text class="s" x="694" y="133">one pair per ResourceRequest</text>
<text class="m dim" x="694" y="172">hello-api-db-&lt;hash&gt;</text>
<rect class="box" x="880" y="70" width="180" height="120" rx="6"/>
<text class="t" x="894" y="96">Secret resource.&lt;rr&gt;</text>
<text class="s" x="894" y="116">password, generated once</text>
<text class="s" x="894" y="133">source of the vcluster copy</text>
<rect class="frame" x="650" y="260" width="430" height="380" rx="8"/>
<text class="cap" x="666" y="282">vcluster env-demo</text>
<rect class="ns" x="666" y="296" width="398" height="140" rx="6"/>
<text class="cap" x="1052" y="314" text-anchor="end">namespace resources</text>
<rect class="box" x="680" y="326" width="180" height="96" rx="6"/>
<text class="t" x="694" y="350">Service shared-pg</text>
<text class="s" x="694" y="369">replicated from the host</text>
<text class="s" x="694" y="386">compose mode</text>
<rect class="box" x="880" y="326" width="170" height="96" rx="6"/>
<text class="t" x="894" y="350">StatefulSet postgres</text>
<text class="s" x="894" y="369">one per request</text>
<text class="s" x="894" y="386">provision mode</text>
<rect class="ns" x="666" y="452" width="398" height="172" rx="6"/>
<text class="cap" x="1052" y="470" text-anchor="end">namespace apps</text>
<rect class="box" x="680" y="486" width="180" height="124" rx="6"/>
<text class="t" x="694" y="510">Deployment hello-api</text>
<text class="m dim" x="694" y="532">PGHOST=</text>
<text class="m dim" x="706" y="548">shared-pg.resources</text>
<text class="m dim" x="694" y="570">PGPASSWORD ←</text>
<text class="m dim" x="706" y="586">secretKeyRef</text>
<rect class="box" x="880" y="486" width="170" height="124" rx="6"/>
<text class="t" x="894" y="510">Secret</text>
<text class="m dim" x="894" y="532">hello-api-db-&lt;hash&gt;</text>
<text class="s" x="894" y="552">password</text>
<path class="edge" d="M240,68 H336" marker-end="url(#fg-arr)"/>
<text class="lbl" x="290" y="60" text-anchor="middle">deploy</text>
<path class="edge hot" d="M240,250 H290 V292 H336" marker-end="url(#fg-arr-hot)"/>
<text class="lbl hot" x="290" y="242" text-anchor="middle">reads resources</text>
<path class="edge hot" d="M240,430 H300 V318 H336" marker-end="url(#fg-arr-hot)"/>
<text class="lbl hot" x="290" y="448" text-anchor="middle">resolves the mode</text>
<path class="edge" d="M455,96 V146" marker-end="url(#fg-arr)"/>
<text class="lbl" x="463" y="127">writes</text>
<path class="edge" d="M455,206 V258" marker-end="url(#fg-arr)"/>
<text class="lbl" x="463" y="238">open revision</text>
<path class="edge hot" d="M455,346 V400" marker-end="url(#fg-arr-hot)"/>
<text class="lbl hot" x="463" y="379">creates or reuses</text>
<path class="edge" d="M455,494 V552" marker-end="url(#fg-arr)"/>
<text class="lbl" x="463" y="529">waits for Ready, reads outputs</text>
<path class="edge hot" d="M570,284 H610 V130 H676" marker-end="url(#fg-arr-hot)"/>
<text class="lbl hot" x="602" y="207" text-anchor="middle" transform="rotate(-90 602 207)">CREATE ROLE · DATABASE</text>
<path class="edge hot" d="M570,318 H662" marker-end="url(#fg-arr-hot)"/>
<text class="lbl hot" x="616" y="310" text-anchor="middle">Secrets</text>
<path class="edge" d="M570,588 H676" marker-end="url(#fg-arr)"/>
<text class="lbl" x="625" y="580" text-anchor="middle">applies</text>
<path class="edge" d="M770,486 V426" marker-end="url(#fg-arr)"/>
<text class="lbl" x="778" y="462">connects</text>
<path class="edge dash" d="M770,326 V194" marker-end="url(#fg-arr)"/>
<text class="lbl" x="778" y="244">replicateServices.fromHost</text>
</svg>
</div>
<figcaption>The deploy of <code>hello-api</code> in <code>demo</code>, with the policy on <code>compose</code>. The highlighted arrows are the Forager's work: it creates the role and the database in <code>shared-pg</code> and writes the Secrets, the password in the control plane and a copy in the namespace <code>apps</code> of the vcluster. In <code>provision</code> mode it creates the StatefulSet in the vcluster instead of talking SQL. The Deployment never holds the password, only a <code>secretKeyRef</code>.</figcaption>
</figure>

1. `platform workload deploy` reaches the API, which writes `WorkloadRevision` 10, still open.
2. The Forager sees the open revision and reads the Score in `Version.spec.appSpec`. For each resource (`db: postgres`) it walks the `BindingPolicy`s: the environment's first (`env-demo`), then its profile's (`profile-ephemeral` for an `ephemeral` environment, #329), then the platform default (`platform-default`). The first item that matches `type`, `class` and `id` wins.
3. It creates or reuses the `ResourceRequest` `demo.hello-api.db`, with the mode fixed in `spec`. When the policy now resolves another mode, the resource is left alone and the revision ends as `ResourceModeChanged`.
4. The provisioner of the mode makes the database and writes `outputs` (`host`, `port`, `database`, `username`), `secretRef` and the condition `Ready` to the `status`.
5. Meanwhile the workload provider keeps the revision in `ResourcesPending`. Once the `ResourceRequest` is `Ready`, it replaces `${resources.db.*}` with the `outputs`, turns the password into a `secretKeyRef` and applies the Deployment.
6. On `workload remove`, the `ResourceRequest`s are deleted and the Forager's finalizer undoes each one: `DROP DATABASE` and `DROP ROLE` in `compose`, the StatefulSet and the Secrets in `provision`.

## The three modes

<figure class="forager-figure" markdown="0">
<div class="forager-scroll">
<svg viewBox="0 0 990 330" role="img" aria-label="The three modes: provision makes a Postgres inside the vcluster; compose makes a database in a shared instance outside the vcluster; bind only copies the credentials of a database that already exists, picked by a class.">
<defs>
<marker id="fg-arr2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path class="head" d="M0,0 L10,5 L0,10 z"/></marker>
</defs>
<text class="panel-title" x="15" y="30">provision</text>
<text class="cap" x="315" y="30" text-anchor="end">#304 · default</text>
<rect class="frame" x="15" y="46" width="300" height="120" rx="8"/>
<text class="cap" x="29" y="66">vcluster of the environment</text>
<rect class="box" x="35" y="86" width="100" height="56" rx="6"/>
<text class="t" x="85" y="119" text-anchor="middle">app</text>
<rect class="box" x="190" y="86" width="105" height="56" rx="6"/>
<text class="t" x="242" y="112" text-anchor="middle">postgres</text>
<text class="s" x="242" y="129" text-anchor="middle">this app only</text>
<path class="edge" d="M135,114 H186" marker-end="url(#fg-arr2)"/>
<text class="s" x="15" y="214">Nothing outside the vcluster.</text>
<text class="s" x="15" y="232">The data goes with the environment.</text>
<text class="panel-title" x="345" y="30">compose</text>
<text class="cap" x="645" y="30" text-anchor="end">#305</text>
<rect class="frame" x="345" y="46" width="300" height="120" rx="8"/>
<text class="cap" x="359" y="66">vcluster of the environment</text>
<rect class="box" x="365" y="86" width="100" height="56" rx="6"/>
<text class="t" x="415" y="119" text-anchor="middle">app</text>
<rect class="frame" x="345" y="196" width="300" height="120" rx="8"/>
<text class="cap" x="359" y="216">host · shared-pg</text>
<rect class="box" x="365" y="232" width="125" height="30" rx="4"/>
<text class="m" x="427" y="251" text-anchor="middle">demo · hello-api</text>
<rect class="box" x="500" y="232" width="125" height="30" rx="4"/>
<text class="m dim" x="562" y="251" text-anchor="middle">qa · orders</text>
<rect class="box" x="365" y="272" width="125" height="30" rx="4"/>
<text class="m dim" x="427" y="291" text-anchor="middle">demo · reviews</text>
<text class="s" x="562" y="291" text-anchor="middle">one per request</text>
<path class="edge" d="M415,142 V228" marker-end="url(#fg-arr2)"/>
<text class="lbl" x="423" y="188">its own database only</text>
<text class="panel-title" x="675" y="30">bind</text>
<text class="cap" x="975" y="30" text-anchor="end">#306 · by class</text>
<rect class="frame" x="675" y="46" width="300" height="120" rx="8"/>
<text class="cap" x="689" y="66">vcluster of the environment</text>
<rect class="box" x="695" y="86" width="100" height="56" rx="6"/>
<text class="t" x="745" y="119" text-anchor="middle">app</text>
<rect class="box" x="850" y="86" width="105" height="56" rx="6"/>
<text class="t" x="902" y="112" text-anchor="middle">Secret</text>
<text class="s" x="902" y="129" text-anchor="middle">copied</text>
<rect class="box" x="675" y="196" width="300" height="120" rx="8"/>
<text class="t" x="689" y="222">a database that exists</text>
<text class="s" x="689" y="242">another team's, or an RDS</text>
<text class="s" x="689" y="262">nothing created or dropped</text>
<path class="edge" d="M745,142 V192" marker-end="url(#fg-arr2)"/>
</svg>
</div>
<figcaption>The policy picks where the database lives, and the Score stays the same in all three: the app gets <code>host</code>, <code>port</code>, <code>database</code>, <code>username</code> and the password through a Secret. An ephemeral environment can use <code>provision</code> while another, with shared data, uses <code>compose</code>, and a branch asks for <code>bind</code> with <code>--resource-class db=restored</code>. Setting the policy: <a href="../environments/#binding-policy">Environments</a>.</figcaption>
</figure>

## dns and route

The same flow reaches an instance from outside its environment (ADR 0036). Every environment has an entry point: the shared Traefik of `platform-local` (`127.0.0.1:7080`) sends `*.<environment>.localhost` to the `Gateway` `platform` of its vcluster.

- `dns/provision` makes nothing: its output `host` is `<instance>.<environment>.localhost`, a name the entry point already routes.
- `route/provision` writes an `HTTPRoute` in `apps`, with `parentRef` on that `Gateway`, the `host` and `path` of its params and the Service of the instance as backend. Its outputs are `host`, `path` and `url`, which the workload provider copies to the instance as `publicUrl`.
- The params of a resource come from the Score (`spec.scoreParams` of the `ResourceRequest`), and `${resources.dns.host}` in them is replaced with the output of the `dns` of the same instance: the `route` stays `Provisioning` until the `dns` is `Ready`. A provisioner reads only the keys of the Score it lists (`route`: `host`, `path`, `port`; `postgres`: none), and the params of the policy item win over them.
- `workload remove` deletes the `HTTPRoute`: the host answers `404` from the `Gateway` again.

## Who writes what

Each object has a single writer of its `status`, so the Forager and the workload provider never race on the same revision.

| Object | Written by | Read by |
|---|---|---|
| `WorkloadRevision` | API (spec), workload provider (status) | Forager |
| `BindingPolicy` | API (`env-<name>` and `profile-<profile>`, `platform-admins` only), `platform init` (`platform-default`, and `profile-ephemeral` when missing) | Forager |
| `ResourceRequest` | **Forager** (spec and status) | workload provider |
| catalog `Resource` | **Forager**, when the Score has no `id` (`hello-api-db`) | API, Backstage |
| database and Secrets | the **provisioner** of the mode, inside the Forager | the app, through `secretKeyRef` |
| `HTTPRoute` in the vcluster (`route`) | the **provisioner** `route/provision`, inside the Forager | the `Gateway` of the environment |
| Deployment in the vcluster | workload provider | the vcluster |

Walkthrough: [A database for a workload](../walkthrough/workloads/resources.md), [A database in the shared instance](../walkthrough/workloads/compose.md) and [Reach an instance from outside](../walkthrough/workloads/public.md).
