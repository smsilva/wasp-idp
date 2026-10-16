# Build from a branch

<div class="turn you" markdown>
<p class="intent">Builds feat/seat-pick and returns its version</p>

```text
Build the feat/seat-pick branch of seat-selection and tell me the version it registers.
```

</div>

<ul class="tool-calls">
  <li><code class="tool">builds_create</code><span><code>seat-selection</code>, <code>feat/seat-pick</code></span></li>
  <li><code class="tool">builds_get</code><span>until it is <code>ready</code>, about a minute</span></li>
  <li><code class="tool">builds_versions_list</code><span>the version the build registered</span></li>
</ul>

The platform dispatches the repo's CI workflow, as in `platform build create`. Check it from the CLI:

```bash
platform build list --component seat-selection
```
