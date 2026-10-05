// Breadcrumb trail of an entity page (#130): the chain of `partOf` parents,
// root domain first (communication > messaging > greeter for greeting-api).
// Components, APIs and Resources are part of a System, a System of a Domain,
// and a subdomain of its parent Domain; each level is one catalog lookup.

export type BreadcrumbEntity = {
  kind: string;
  metadata: { name: string; namespace?: string; title?: string };
  relations?: { type: string; targetRef: string }[];
};

export type Breadcrumb = {
  ref: string;
  kind: string;
  name: string;
  title?: string;
};

const refOf = (entity: BreadcrumbEntity) =>
  `${entity.kind}:${entity.metadata.namespace ?? 'default'}/${
    entity.metadata.name
  }`.toLocaleLowerCase('en-US');

const parentOf = (entity: BreadcrumbEntity) =>
  entity.relations?.find(
    relation =>
      relation.type === 'partOf' &&
      /^(system|domain):/.test(relation.targetRef),
  )?.targetRef;

// More levels than any real hierarchy; guards against runaway chains
const MAX_DEPTH = 8;

export async function loadBreadcrumbs(
  entity: BreadcrumbEntity,
  getEntityByRef: (ref: string) => Promise<BreadcrumbEntity | undefined>,
): Promise<Breadcrumb[]> {
  const trail: Breadcrumb[] = [];
  const seen = new Set([refOf(entity)]);
  let parentRef = parentOf(entity);
  while (parentRef && !seen.has(parentRef) && trail.length < MAX_DEPTH) {
    seen.add(parentRef);
    const [kind, rest] = parentRef.split(':');
    const parent = await getEntityByRef(parentRef);
    trail.unshift({
      ref: parentRef,
      kind,
      name: parent?.metadata.name ?? rest.split('/')[1],
      title: parent?.metadata.title,
    });
    parentRef = parent ? parentOf(parent) : undefined;
  }
  return trail;
}
