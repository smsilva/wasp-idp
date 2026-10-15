# Wrap up

<div class="turn you" markdown>
<p class="intent">Deletes agent-demo</p>

```text
Delete the agent-demo environment.
```

</div>

<ul class="tool-calls">
  <li><code class="tool">environments_delete</code><span>only <code>ephemeral</code> environments: a <code>shared</code> one is deleted with <code>platform environment delete</code></span></li>
</ul>

Back to the read-only server:

```bash
claude mcp remove \
  --scope user \
  platform
```

```bash
claude mcp add platform \
  --scope user -- \
    platform-mcp \
      --toolsets core,environments,catalog,builds,workloads
```
