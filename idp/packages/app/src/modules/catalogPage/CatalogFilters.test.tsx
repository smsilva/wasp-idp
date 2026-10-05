import { fireEvent, screen, waitFor } from '@testing-library/react';
import { mockApis, renderInTestApp } from '@backstage/frontend-test-utils';
import {
  MockStarredEntitiesApi,
  starredEntitiesApiRef,
} from '@backstage/plugin-catalog-react';
import {
  catalogApiMock,
  MockEntityListContextProvider,
} from '@backstage/plugin-catalog-react/testUtils';
import { CatalogFilters } from './CatalogFilters';

const entity = (
  kind: string,
  name: string,
  owner: string,
  lifecycle?: string,
) => ({
  apiVersion: 'backstage.io/v1alpha1',
  kind,
  metadata: { name, namespace: 'default' },
  spec: { owner, ...(lifecycle && { type: 'service', lifecycle }) },
  relations: [{ type: 'ownedBy', targetRef: `group:default/${owner}` }],
});

const entities = [
  entity('Domain', 'communication', 'team-alpha'),
  entity('Component', 'greeting-api', 'team-alpha', 'experimental'),
  entity('Component', 'notification-api', 'team-beta', 'production'),
];

function renderFilters(updateFilters = jest.fn()) {
  return {
    updateFilters,
    ...renderInTestApp(
      <MockEntityListContextProvider value={{ updateFilters }}>
        <CatalogFilters />
      </MockEntityListContextProvider>,
      {
        apis: [
          catalogApiMock({ entities }),
          mockApis.identity({
            userEntityRef: 'user:default/guest',
            ownershipEntityRefs: ['group:default/team-alpha'],
          }),
          [starredEntitiesApiRef, new MockStarredEntitiesApi()],
        ],
      },
    ),
  };
}

describe('CatalogFilters', () => {
  it('lists every kind with its count, component selected by default', async () => {
    renderFilters();
    const component = await screen.findByRole('button', {
      name: /^Component\s*2$/,
    });
    expect(component).toHaveAttribute('aria-pressed', 'true');
    expect(
      screen.getByRole('button', { name: /^Domain\s*1$/ }),
    ).toHaveAttribute('aria-pressed', 'false');
  });

  it('switches kind and resets the type filter', async () => {
    const { updateFilters } = renderFilters();
    fireEvent.click(
      await screen.findByRole('button', { name: /^Domain\s*1$/ }),
    );
    expect(updateFilters).toHaveBeenLastCalledWith(
      expect.objectContaining({
        kind: expect.objectContaining({ value: 'domain' }),
        type: undefined,
      }),
    );
  });

  it('counts owned entities from the identity and offers facet values', async () => {
    const { updateFilters } = renderFilters();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^Owned\s*1$/ })).toBeEnabled(),
    );
    const lifecycle = await screen.findByLabelText('Lifecycle');
    await screen.findByRole('option', { name: 'production' });
    fireEvent.change(lifecycle, { target: { value: 'production' } });
    expect(updateFilters).toHaveBeenLastCalledWith({
      lifecycles: expect.objectContaining({ values: ['production'] }),
    });
  });
});

describe('CatalogFilters collapse', () => {
  afterEach(() => window.localStorage.clear());

  it('collapses to a toggle and remembers it', async () => {
    renderFilters();
    fireEvent.click(
      await screen.findByRole('button', { name: 'Hide filters' }),
    );
    expect(
      screen.getByRole('button', { name: 'Show filters' }),
    ).toBeInTheDocument();
    expect(screen.queryByText('Kind')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('catalogFiltersCollapsed')).toBe('true');
  });
});
