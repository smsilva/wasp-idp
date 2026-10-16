# The catalog

<div class="turn you" markdown>
<p class="intent">Retrieves Systems, components and the creation of seat-selection</p>

```text
Which systems does team-airport own, which components belong to seat-map, and how was seat-selection created?
```

</div>

<ul class="tool-calls">
  <li><code class="tool">catalog_list</code><span>systems of <code>team-airport</code></span></li>
  <li><code class="tool">catalog_get</code><span><code>seat-map</code> with its dependents</span></li>
  <li><code class="tool">catalog_components_list</code><span>components of <code>seat-map</code></span></li>
  <li><code class="tool">catalog_components_get</code><span><code>seat-selection</code>, with its newest builds and versions and where it runs</span></li>
  <li><code class="tool">catalog_components_creation_get</code><span>the steps that created <code>seat-selection</code></span></li>
</ul>
