// Identity block of the entity page header (#130, option B of
// docs/idp/design/entity-header/header-options.html): labelled breadcrumb,
// kind icon, title with KIND · TYPE, description, and a column of facts
// (label above value) next to the actions. The BUI Header renders breadcrumbs
// inline with the title and has no slot for an icon, so this block sits above
// it and the Header keeps only the tabs.
import { ReactNode, useEffect, useState } from 'react';
import { useApi } from '@backstage/core-plugin-api';
import {
  catalogApiRef,
  useAsyncEntity,
  useEntityPresentation,
  useEntityRefLink,
} from '@backstage/plugin-catalog-react';
import { Link } from '@backstage/ui';
import { Breadcrumb, loadBreadcrumbs } from './breadcrumbs';
import styles from './EntityIdentity.module.css';

type Entity = NonNullable<ReturnType<typeof useAsyncEntity>['entity']>;

export type Fact = { label: string; value: ReactNode; emphasis?: boolean };

function useBreadcrumbs(entity: Entity | undefined) {
  const catalogApi = useApi(catalogApiRef);
  const [crumbs, setCrumbs] = useState<Breadcrumb[]>([]);
  useEffect(() => {
    if (!entity) return undefined;
    let cancelled = false;
    loadBreadcrumbs(entity, ref => catalogApi.getEntityByRef(ref))
      .then(trail => !cancelled && setCrumbs(trail))
      .catch(() => !cancelled && setCrumbs([]));
    return () => {
      cancelled = true;
    };
  }, [catalogApi, entity]);
  return crumbs;
}

// "DOMAIN communication › messaging › SYSTEM greeter": the kind label is shown
// once, where the kind changes along the trail. Entities without parents show
// a link back to the catalog.
function Breadcrumbs({ crumbs }: { crumbs: Breadcrumb[] }) {
  const entityLink = useEntityRefLink();
  if (crumbs.length === 0) {
    return (
      <nav className={styles.crumbs} aria-label="Breadcrumb">
        <Link href="/" standalone color="secondary">
          Catalog
        </Link>
      </nav>
    );
  }
  return (
    <nav className={styles.crumbs} aria-label="Breadcrumb">
      {crumbs.map((crumb, index) => {
        const kindChanged =
          index === 0 || crumbs[index - 1].kind !== crumb.kind;
        return (
          <span key={crumb.ref} className={styles.crumb}>
            {index > 0 && !kindChanged && (
              <span className={styles.sep} aria-hidden="true">
                ›
              </span>
            )}
            {kindChanged && (
              <span className={styles.crumbKind}>{crumb.kind}</span>
            )}
            <Link href={entityLink(crumb.ref)} standalone color="secondary">
              {crumb.title ?? crumb.name}
            </Link>
          </span>
        );
      })}
    </nav>
  );
}

export function EntityIdentity({
  entity,
  fallbackRef,
  facts,
  actions,
}: {
  entity: Entity | undefined;
  fallbackRef: { kind: string; namespace: string; name: string };
  facts: Fact[];
  actions: ReactNode;
}) {
  const presentation = useEntityPresentation(entity ?? fallbackRef);
  const crumbs = useBreadcrumbs(entity);
  const Icon = presentation.Icon;
  const type = entity?.spec?.type;
  const kind = entity?.kind ?? fallbackRef.kind;
  const tags = entity?.metadata.tags ?? [];

  return (
    <div className={styles.root}>
      <Breadcrumbs crumbs={crumbs} />
      <div className={styles.grid}>
        <div className={styles.ident}>
          <span className={styles.glyph} aria-hidden="true">
            {Icon ? <Icon fontSize="inherit" /> : null}
          </span>
          <h1 className={styles.title}>
            {presentation.primaryTitle}
            <small className={styles.kind}>
              {type ? `${kind} · ${String(type)}` : kind}
            </small>
          </h1>
          {(entity?.metadata.description || tags.length > 0) && (
            <p className={styles.desc}>
              {entity?.metadata.description}
              {tags.map(tag => (
                <span key={tag} className={styles.tag}>
                  {tag}
                </span>
              ))}
            </p>
          )}
        </div>
        <div className={styles.side}>
          {facts.length > 0 && (
            <dl className={styles.facts}>
              {facts.map(fact => (
                <div key={fact.label}>
                  <dt>{fact.label}</dt>
                  <dd className={fact.emphasis ? styles.emphasis : undefined}>
                    {fact.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <div className={styles.actions}>{actions}</div>
        </div>
      </div>
    </div>
  );
}
