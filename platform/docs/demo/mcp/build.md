# Build from a branch

<div class="turn you" markdown>
<p class="intent">Builds feat/greetings and returns its version</p>

```text
Build the feat/greetings branch of hello-api and tell me the version it registers.
```

</div>

<ul class="tool-calls">
  <li><code class="tool">builds_create</code><span><code>hello-api</code>, <code>feat/greetings</code></span></li>
  <li><code class="tool">builds_get</code><span>until it is <code>ready</code>, about a minute</span></li>
  <li><code class="tool">builds_versions_list</code><span>the version the build registered</span></li>
</ul>

The platform dispatches the repo's CI workflow, as in `platform build create`. Check it from the CLI:

```bash
platform build list --component hello-api
```
