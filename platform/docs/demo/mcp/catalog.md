# The catalog

<div class="turn you" markdown>
<p class="intent">Retrieves Systems, components and the creation of hello-api</p>

```text
Which systems does team-alpha own, which components belong to greeter, and how was hello-api created?
```

</div>

<ul class="tool-calls">
  <li><code class="tool">catalog_list</code><span>systems of <code>team-alpha</code></span></li>
  <li><code class="tool">catalog_get</code><span><code>greeter</code> with its dependents</span></li>
  <li><code class="tool">catalog_components_list</code><span>components of <code>greeter</code></span></li>
  <li><code class="tool">catalog_components_get</code><span><code>hello-api</code>, with its newest builds and versions and where it runs</span></li>
  <li><code class="tool">catalog_components_creation_get</code><span>the steps that created <code>hello-api</code></span></li>
</ul>
