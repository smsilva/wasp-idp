// Compact catalog filter column (option A of
// docs/idp/design/catalog-filters/options.html): every kind visible with its
// count, Owned/Starred/All as one segmented row, and the remaining filters as
// "label → value" rows. It drives the stock filter classes through
// useEntityList, so the table, the URL query string and the counts behave as
// with the stock pickers it replaces.
import { useEffect, useMemo, useState } from 'react';
import { LuPanelLeftClose, LuPanelLeftOpen } from 'react-icons/lu';
import { identityApiRef, useApi } from '@backstage/core-plugin-api';
import {
  catalogApiRef,
  EntityErrorFilter,
  EntityKindFilter,
  EntityLifecycleFilter,
  EntityNamespaceFilter,
  EntityOrphanFilter,
  EntityOwnerFilter,
  EntityTagFilter,
  EntityTypeFilter,
  EntityUserFilter,
  useEntityList,
  useStarredEntities,
} from '@backstage/plugin-catalog-react';
import styles from './CatalogFilters.module.css';

type Facets = Record<string, Array<{ value: string; count: number }>>;
type ListId = 'owned' | 'starred' | 'all';
type Filters = ReturnType<typeof useEntityList>['filters'];

const KIND_ORDER = ['domain', 'system', 'component', 'api', 'resource'];

// Value filters shown as rows. `extra` rows stay behind "More filters".
const FIELDS = [
  {
    key: 'owners',
    label: 'Owner',
    facet: 'relations.ownedBy',
    make: (v: string) => new EntityOwnerFilter([v]),
    current: (f: Filters) => f.owners?.values[0],
  },
  {
    key: 'type',
    label: 'Type',
    facet: 'spec.type',
    make: (v: string) => new EntityTypeFilter(v),
    current: (f: Filters) => f.type?.getTypes()[0],
  },
  {
    key: 'lifecycles',
    label: 'Lifecycle',
    facet: 'spec.lifecycle',
    make: (v: string) => new EntityLifecycleFilter([v]),
    current: (f: Filters) => f.lifecycles?.values[0],
  },
  {
    key: 'tags',
    label: 'Tags',
    facet: 'metadata.tags',
    make: (v: string) => new EntityTagFilter([v]),
    current: (f: Filters) => f.tags?.values[0],
  },
  {
    key: 'namespace',
    label: 'Namespace',
    facet: 'metadata.namespace',
    make: (v: string) => new EntityNamespaceFilter([v]),
    current: (f: Filters) => f.namespace?.values[0],
    extra: true,
  },
] as const;

const first = (value: string | string[] | undefined) => [value].flat()[0];

// "group:default/team-alpha" → "team-alpha"
const shortRef = (ref: string) =>
  ref.replace(/^[^:]+:/, '').replace(/^default\//, '');

const kindLabel = (kind: string) =>
  kind === 'api' ? 'API' : kind.charAt(0).toUpperCase() + kind.slice(1);

function useKindCounts(userFilter: EntityUserFilter | undefined) {
  const catalogApi = useApi(catalogApiRef);
  const [counts, setCounts] = useState<Map<string, number>>(new Map());
  const filter = useMemo(
    () => userFilter?.getCatalogFilters() ?? {},
    [userFilter],
  );
  useEffect(() => {
    let cancelled = false;
    catalogApi
      .getEntityFacets({ facets: ['kind'], filter })
      .then(({ facets }) => {
        if (cancelled) return;
        setCounts(
          new Map(
            facets.kind.map(f => [f.value.toLocaleLowerCase('en-US'), f.count]),
          ),
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [catalogApi, filter]);
  return counts;
}

function useListCounts(
  kind: string | undefined,
  ownershipRefs: string[] | undefined,
) {
  const catalogApi = useApi(catalogApiRef);
  const { starredEntities } = useStarredEntities();
  const [counts, setCounts] = useState<Record<ListId, number | undefined>>({
    owned: undefined,
    starred: undefined,
    all: undefined,
  });
  useEffect(() => {
    if (!kind || !ownershipRefs) return undefined;
    let cancelled = false;
    const total = (filter: Record<string, string | string[]>) =>
      catalogApi
        .queryEntities({ filter: { kind, ...filter }, limit: 0 })
        .then(r => r.totalItems);
    Promise.all([
      ownershipRefs.length ? total({ 'relations.ownedBy': ownershipRefs }) : 0,
      total({}),
    ])
      .then(([owned, all]) => {
        if (cancelled) return;
        const starred = [...starredEntities].filter(ref =>
          ref.startsWith(`${kind.toLocaleLowerCase('en-US')}:`),
        ).length;
        setCounts({ owned, starred, all });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [catalogApi, kind, ownershipRefs, starredEntities]);
  return counts;
}

function useFieldFacets(kind: string | undefined) {
  const catalogApi = useApi(catalogApiRef);
  const [facets, setFacets] = useState<Facets>({});
  useEffect(() => {
    if (!kind) return undefined;
    let cancelled = false;
    catalogApi
      .getEntityFacets({ facets: FIELDS.map(f => f.facet), filter: { kind } })
      .then(r => !cancelled && setFacets(r.facets))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [catalogApi, kind]);
  return facets;
}

// Collapsed state survives reloads, like the sidebar pin state.
const COLLAPSED_KEY = 'catalogFiltersCollapsed';

function useCollapsed() {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem(COLLAPSED_KEY) === 'true';
    } catch {
      return false;
    }
  });
  const toggle = () => {
    setCollapsed(!collapsed);
    try {
      window.localStorage.setItem(COLLAPSED_KEY, String(!collapsed));
    } catch {
      // localStorage unavailable: the state just does not persist
    }
  };
  return [collapsed, toggle] as const;
}

export function CatalogFilters(props: { initialKind?: string }) {
  const { initialKind = 'component' } = props;
  const { filters, updateFilters, queryParameters } = useEntityList();
  const identityApi = useApi(identityApiRef);
  const { starredEntities } = useStarredEntities();
  const [ownershipRefs, setOwnershipRefs] = useState<string[]>();
  const [showMore, setShowMore] = useState(false);
  const [collapsed, toggleCollapsed] = useCollapsed();

  const kind =
    filters.kind?.value ?? first(queryParameters.kind) ?? initialKind;
  const [list, setList] = useState<ListId>(
    (first(queryParameters.user) as ListId | undefined) ?? 'owned',
  );

  useEffect(() => {
    identityApi
      .getBackstageIdentity()
      .then(identity => setOwnershipRefs(identity.ownershipEntityRefs))
      .catch(() => setOwnershipRefs([]));
  }, [identityApi]);

  const kindCounts = useKindCounts(
    filters.user as EntityUserFilter | undefined,
  );
  const listCounts = useListCounts(kind, ownershipRefs);
  const facets = useFieldFacets(kind);

  // Seed the value filters from the URL once, like the stock pickers do.
  useEffect(() => {
    const initial: Partial<Filters> = {
      kind: new EntityKindFilter(kind, kindLabel(kind)),
    };
    for (const field of FIELDS) {
      const value = first(queryParameters[field.key]);
      if (value) Object.assign(initial, { [field.key]: field.make(value) });
    }
    updateFilters(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Same rule as the stock UserListPicker: an empty Owned/Starred falls back to All.
  const effectiveList: ListId =
    list !== 'all' && listCounts[list] === 0 ? 'all' : list;
  useEffect(() => {
    if (!ownershipRefs) return;
    const users: Record<ListId, () => EntityUserFilter> = {
      owned: () => EntityUserFilter.owned(ownershipRefs),
      starred: () => EntityUserFilter.starred([...starredEntities]),
      all: () => EntityUserFilter.all(),
    };
    updateFilters({ user: users[effectiveList]() });
  }, [effectiveList, ownershipRefs, starredEntities, updateFilters]);

  const selectKind = (value: string) =>
    updateFilters({
      kind: new EntityKindFilter(value, kindLabel(value)),
      type: undefined,
    });

  let status = '';
  if (filters.orphan?.value) status = 'orphan';
  else if (filters.error?.value) status = 'error';
  const activeCount =
    FIELDS.filter(field => field.current(filters)).length + (status ? 1 : 0);
  const active = activeCount > 0;

  const kinds = [...kindCounts.keys()].sort(
    (a, b) =>
      (KIND_ORDER.indexOf(a) + 1 || 99) - (KIND_ORDER.indexOf(b) + 1 || 99) ||
      a.localeCompare(b),
  );
  if (!kinds.includes(kind)) kinds.push(kind);

  if (collapsed) {
    return (
      <div className={styles.root} data-collapsed="true">
        <button
          type="button"
          className={styles.toggle}
          aria-label="Show filters"
          title="Show filters"
          onClick={toggleCollapsed}
        >
          <LuPanelLeftOpen aria-hidden />
          {active && <span className={styles.badge}>{activeCount}</span>}
        </button>
      </div>
    );
  }

  return (
    <div className={styles.root}>
      <div className={styles.head}>
        <h2 className={styles.title}>Filters</h2>
        <button
          type="button"
          className={styles.toggle}
          aria-label="Hide filters"
          title="Hide filters"
          onClick={toggleCollapsed}
        >
          <LuPanelLeftClose aria-hidden />
        </button>
      </div>
      <div>
        <p className={styles.groupTitle} id="catalog-filter-kind">
          Kind
        </p>
        <div
          className={styles.kinds}
          role="group"
          aria-labelledby="catalog-filter-kind"
        >
          {kinds.map(k => (
            <button
              key={k}
              type="button"
              className={styles.kind}
              aria-pressed={k === kind}
              onClick={() => selectKind(k)}
            >
              {kindLabel(k)}
              <span className={styles.count}>{kindCounts.get(k) ?? 0}</span>
            </button>
          ))}
        </div>
      </div>

      <div className={styles.segmented} role="group" aria-label="List">
        {(['owned', 'starred', 'all'] as const).map(id => (
          <button
            key={id}
            type="button"
            aria-pressed={id === effectiveList}
            disabled={id !== 'all' && listCounts[id] === 0}
            onClick={() => setList(id)}
          >
            {id.charAt(0).toUpperCase() + id.slice(1)}
            <span className={styles.count}>{listCounts[id] ?? ''}</span>
          </button>
        ))}
      </div>

      <div className={styles.props}>
        {FIELDS.map(field => {
          const current = field.current(filters);
          const values = facets[field.facet] ?? [];
          if (!values.length && !current) return null;
          if ('extra' in field && !showMore && !current) return null;
          const id = `catalog-filter-${field.key}`;
          return (
            <div
              key={field.key}
              className={styles.prop}
              data-active={Boolean(current)}
            >
              <label htmlFor={id}>{field.label}</label>
              <select
                id={id}
                value={current ?? ''}
                onChange={e =>
                  updateFilters({
                    [field.key]: e.target.value
                      ? field.make(e.target.value)
                      : undefined,
                  })
                }
              >
                <option value="">Any</option>
                {[...values]
                  .sort((a, b) => a.value.localeCompare(b.value))
                  .map(({ value }) => (
                    <option key={value} value={value}>
                      {field.key === 'owners' ? shortRef(value) : value}
                    </option>
                  ))}
              </select>
            </div>
          );
        })}
        {(showMore || status) && (
          <div className={styles.prop} data-active={Boolean(status)}>
            <label htmlFor="catalog-filter-status">Status</label>
            <select
              id="catalog-filter-status"
              value={status}
              onChange={e =>
                updateFilters({
                  orphan:
                    e.target.value === 'orphan'
                      ? new EntityOrphanFilter(true)
                      : undefined,
                  error:
                    e.target.value === 'error'
                      ? new EntityErrorFilter(true)
                      : undefined,
                })
              }
            >
              <option value="">Any</option>
              <option value="orphan">Is orphan</option>
              <option value="error">Has error</option>
            </select>
          </div>
        )}
      </div>

      <div className={styles.footer}>
        <button
          type="button"
          className={styles.more}
          aria-expanded={showMore}
          onClick={() => setShowMore(!showMore)}
        >
          {showMore ? 'Fewer filters' : 'More filters'}
        </button>
        {active && (
          <button
            type="button"
            className={styles.clear}
            onClick={() =>
              updateFilters({
                owners: undefined,
                type: undefined,
                lifecycles: undefined,
                tags: undefined,
                namespace: undefined,
                orphan: undefined,
                error: undefined,
              })
            }
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
}
