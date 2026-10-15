# Create an environment

<div class="turn you" markdown>
<p class="intent">Creates agent-demo and waits until it is ready</p>

```text
Create an ephemeral environment called agent-demo for 2 hours and tell me when it is ready.
```

</div>

<ul class="tool-calls">
  <li><code class="tool">environments_create</code><span><code>agent-demo</code>, <code>ephemeral</code>, <code>expires: 2h</code></span></li>
  <li><code class="tool">environments_get</code><span>until it is <code>ready</code></span></li>
</ul>

The server refuses an environment without an expiration. Check it from the CLI:

```bash
platform environment list
```
