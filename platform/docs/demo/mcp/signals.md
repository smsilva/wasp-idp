# What runs and how it behaves

<div class="turn you" markdown>
<p class="intent">Retrieves what runs, its signals and its deploy history</p>

```text
What runs in agent-demo, how is seat-selection doing, and which versions were deployed there?
```

</div>

<ul class="tool-calls">
  <li><code class="tool">workloads_list</code><span>the instances in <code>agent-demo</code>, with version and URL</span></li>
  <li><code class="tool">workloads_signals</code><span>latency p95, traffic, errors and saturation of <code>seat-selection</code>, from the mesh</span></li>
  <li><code class="tool">workloads_history</code><span>each revision, newest first</span></li>
</ul>
