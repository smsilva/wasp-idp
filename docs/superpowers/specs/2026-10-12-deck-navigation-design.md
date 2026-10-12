# Deck navigation: diagram as the main track, details on click

Issue: #386.

## Problem

The deck walks the landscape diagram box by box, but each box opens its full detail inline. After `landscape-dev-1` (Software Catalog) come 22 slides before the diagram returns in `landscape-dev-2`. The diagram is the anchor of the talk and it disappears for too long; the flow feels broken when it comes back.

## Goal

- The main track (→ without clicking) walks only the diagram: a plane in focus, its boxes revealed one per step, the current box in focus.
- A box's detail is opened by clicking the box, from the plane opening or from the final picture (`landscape-full`).
- In a detail, the presenter always knows where they are (breadcrumb, fixed) and can return to where they came from (back, a stack).

## Main track

`landscape-dev-1`, `landscape-dev-2` and `landscape-dev-3` become one slide, `landscape-dev`:

```yaml
- name: landscape-dev
  act: developer-control
  topic: "Developer Control Plane"
  divider: "Developer Control Plane"
  heading: "Developer Control Plane"
  diagram: "diagrams/landscape/landscape.svg"
  show: [dev-plane, ind-plane, res-plane, obs-plane, sec-plane]
  focus: [dev-plane]
  start: "empty"
  reveal: [dev.1, dev.2, dev.3]
  accumulate: true
  spotlight: true
  links: {dev.1: detail-catalog, dev.2: detail-app-declaration, dev.3: detail-golden-paths}
```

- `focus: [<part>]`: the part's border is highlighted on every step of the slide.
- `spotlight: true`: the part revealed in the step is highlighted too, so the current box stands out from the ones already revealed.
- `links: {<part>: <slide>}`: the part is clickable in presentation mode and opens that slide. A hidden part is not clickable.

`landscape-full` gets the same `links` for the three boxes. The other planes stay linear in this cut.

## Detail slides

A slide with `parent: <slide>` is a detail slide:

- It leaves the main track. Its steps go to an appendix after the last main step, in YAML order. The YAML keeps the slides where they are, so `dependsOn` stays valid.
- No divider and no agenda step before it.
- Its label is `label`, else `heading`. A detail slide with neither is a validation error.

A **root** is a detail slide whose parent is a main-track slide. A root is a diagram slide: the clicked box is active and in focus, and everything else is dimmed. It also has an **overlay**, a panel over the right side of the diagram with the root label and its direct children as links.

```yaml
- name: detail-catalog
  act: developer-control
  topic: "Software Catalog"
  parent: landscape-dev
  heading: "Software Catalog"
  diagram: "diagrams/landscape/landscape.svg"
  dim: [dev-plane, ind-plane, res-plane, obs-plane, sec-plane, dev.2, dev.3]
  show: [dev.1]
  focus: [dev.1]
```

### Software Catalog tree

The existing slides, unchanged in content, are attached with `parent`:

- `detail-catalog` (overlay: the six items below)
  - `catalog-ownership`: The catalog answers
  - `catalog-levels`: The catalog has two views
    - `catalog-business-view`
      - `entity-system`, `entity-domain`
    - `catalog-engineering-view`
      - `entity-component`, `entity-api`, `entity-resource`
  - `spotify-tree`: Spotify demo catalog
  - `catalog-tree`: Our catalog
  - `declare-name`, label "catalog-info.yaml"
    - `declare-system`, `declare-ownership`, `ip-lifecycle`, `declare-apis`, `declare-dependencies`, `declare-discovery`
  - `no-versions`: What the catalog stores
    - `major-breaking`, `plugins`

The code slides (`declare-*`) get a `label` (System, Ownership, APIs, Dependencies).

### App Declaration and Golden Paths

- `detail-app-declaration` → `spec-db` (Resources), `spec-variables` (Variables), `spec-route` (Route), `spec-service` (Service), `score-what-not`.
- `detail-golden-paths` → `golden-paths`.

The notes of `landscape-dev-1/2/3` move to the roots. `landscape-dev` gets a short note covering the three boxes.

## Navigation

- **Breadcrumb (where I am):** built from the `parent` chain and shown in place of the act name on every detail slide: `Platform › Developer Control Plane › Software Catalog › Two views`. Each level is a link to that slide's first step. `Platform` is `deck.home` (`landscape-full`).
- **Back (where I came from):** a stack of step indexes in `sessionStorage`. Following a link (box, overlay item, breadcrumb) from a main-track step into a detail step pushes the origin step. "↩ back", next to the breadcrumb, and Backspace (on a detail step) pop it and show that step. With an empty stack (detail opened from a direct link or from the index), back goes to the parent slide.
- **→ and ←:**
  - inside a detail, → and ← walk the steps of its subtree in YAML order;
  - → on the last step of a root's subtree acts as back;
  - ← on the root's first step acts as back;
  - → on the last main-track step does not enter the appendix.
- Agenda items of Developer Control Plane point to the three roots; the agenda part range covers main-track steps only.

## Rendering (`render-outline`)

- `build_steps` builds main-track steps first, then the detail steps, and marks each step with `detail`, `root` (its subtree root) and `exit` (the last step of a subtree).
- Diagram parts take a set of classes: `part-on|dim|hidden` plus `part-focus` (the first `rect` of the group gets a highlighted stroke). Linked parts get `data-go-slide` and `part-link` (pointer cursor).
- Links resolve in JS through the existing `.stage[data-slide=<name>]`. Clicks are handled only on `[data-go-slide]`, so a click elsewhere still never navigates.
- `validate`: `parent` and `links` targets exist; no cycle; a root has a `diagram`; every detail slide has a label.
- `CONTRIBUTING.md` documents `parent`, `label`, `focus`, `spotlight`, `links` and `deck.home`.

## Testing

- `./render-outline idp.yaml` passes validation.
- In Chrome:
  - the main track goes from the Developer Control Plane opening straight to Integration & Delivery;
  - clicking each box from `landscape-dev` and from `landscape-full` opens its root, and back returns to the origin step;
  - → at the end of the Software Catalog subtree returns to the origin;
  - the breadcrumb links work;
  - `#present-detail-catalog`, opened directly, falls back to `landscape-dev`.

## Out of scope

- The other planes (Integration & Delivery, Resource, Observability & Security) and the API.
- Visited marks on the diagram (decision: the diagram returns exactly as it was left).
- Concept links inside text slides.
