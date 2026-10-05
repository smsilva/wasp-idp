import { BreadcrumbEntity, loadBreadcrumbs } from './breadcrumbs';

const entity = (
  kind: string,
  name: string,
  partOf: string[] = [],
): BreadcrumbEntity => ({
  kind,
  metadata: { name, namespace: 'default' },
  relations: partOf.map(targetRef => ({ type: 'partOf', targetRef })),
});

// The communication example: communication > messaging > greeter > greeting-api
const catalog = new Map(
  [
    entity('Domain', 'communication'),
    entity('Domain', 'messaging', ['domain:default/communication']),
    entity('System', 'greeter', ['domain:default/messaging']),
    entity('Component', 'greeting-api', ['system:default/greeter']),
    entity('Domain', 'loop-a', ['domain:default/loop-b']),
    entity('Domain', 'loop-b', ['domain:default/loop-a']),
  ].map(item => [
    `${item.kind}:default/${item.metadata.name}`.toLocaleLowerCase('en-US'),
    item,
  ]),
);

const getEntityByRef = async (ref: string) => catalog.get(ref);

describe('loadBreadcrumbs', () => {
  it('walks partOf up to the root domain, outermost first', async () => {
    const crumbs = await loadBreadcrumbs(
      catalog.get('component:default/greeting-api')!,
      getEntityByRef,
    );
    expect(crumbs.map(c => [c.kind, c.name])).toEqual([
      ['domain', 'communication'],
      ['domain', 'messaging'],
      ['system', 'greeter'],
    ]);
  });

  it('returns nothing for a root domain', async () => {
    expect(
      await loadBreadcrumbs(
        catalog.get('domain:default/communication')!,
        getEntityByRef,
      ),
    ).toEqual([]);
  });

  it('keeps the ref when a parent is missing from the catalog', async () => {
    const orphan = entity('System', 'lost', ['domain:default/gone']);
    const crumbs = await loadBreadcrumbs(orphan, getEntityByRef);
    expect(crumbs.map(c => c.ref)).toEqual(['domain:default/gone']);
  });

  it('stops on a partOf cycle without repeating the current entity', async () => {
    const crumbs = await loadBreadcrumbs(
      catalog.get('domain:default/loop-a')!,
      getEntityByRef,
    );
    expect(crumbs.map(c => c.name)).toEqual(['loop-b']);
  });
});
