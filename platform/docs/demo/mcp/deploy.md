# Deploy it

<div class="turn you" markdown>
<p class="intent">Deploys the version to agent-demo and returns its URL</p>

```text
Deploy the version you just built to agent-demo and tell me when it runs.
```

</div>

<ul class="tool-calls">
  <li><code class="tool">workloads_deploy</code><span><code>agent-demo</code>, <code>hello-api</code>, the version from the build</span></li>
  <li><code class="tool">workloads_history</code><span>until the revision closes, <code>Succeeded</code></span></li>
  <li><code class="tool">workloads_get</code><span>the URL of <code>hello-api</code> in <code>agent-demo</code></span></li>
</ul>

The API answers right away with an open revision, as `platform workload deploy` without `--wait`. Check it from the CLI:

```bash
platform workload get hello-api --environment agent-demo
```
