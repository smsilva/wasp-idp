import {
  coreExtensionData,
  createExtensionInput,
  createFrontendModule,
} from '@backstage/frontend-plugin-api';
import { useEntity } from '@backstage/plugin-catalog-react';
import {
  EntityCardBlueprint,
  EntityContentBlueprint,
} from '@backstage/plugin-catalog-react/alpha';
import { Grid } from '@material-ui/core';
import type { ReactElement } from 'react';

type Entity = ReturnType<typeof useEntity>['entity'];

type DependencyCard = {
  element: ReactElement;
  filter?: (entity: Entity) => boolean;
};

const DependenciesContent = ({ cards }: { cards: DependencyCard[] }) => {
  const { entity } = useEntity();
  return (
    <Grid container spacing={3} alignItems="stretch">
      {cards
        .filter(card => !card.filter || card.filter(entity))
        .map((card, index) => (
          <Grid item xs={12} key={index}>
            {card.element}
          </Grid>
        ))}
    </Grid>
  );
};

// "Dependencies" tab for Components. It renders whatever entity cards are
// attached to its `cards` input: app-config.yaml moves the catalog relation cards
// (depends-on-*, has-subcomponents) here from the Overview tab via attachTo, so
// they stay the stock cards.
const entityDependenciesContent = EntityContentBlueprint.makeWithOverrides({
  name: 'dependencies',
  inputs: {
    cards: createExtensionInput([
      coreExtensionData.reactElement,
      EntityCardBlueprint.dataRefs.filterFunction.optional(),
    ]),
  },
  factory: (originalFactory, { inputs }) =>
    originalFactory({
      path: '/dependencies',
      title: 'Dependencies',
      filter: { kind: 'component' },
      loader: async () => (
        <DependenciesContent
          cards={inputs.cards.map(card => ({
            element: card.get(coreExtensionData.reactElement),
            filter: card.get(EntityCardBlueprint.dataRefs.filterFunction),
          }))}
        />
      ),
    }),
});

export const entityDependenciesModule = createFrontendModule({
  pluginId: 'catalog',
  extensions: [entityDependenciesContent],
});
