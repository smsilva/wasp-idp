import { useEntity } from '@backstage/plugin-catalog-react';
import { InfoCard } from '@backstage/core-components';
import { Chip, Typography } from '@material-ui/core';

// What the About card showed that the header does not: description and tags.
// The tags line only appears when the entity has tags.
export function DescriptionCard() {
  const { entity } = useEntity();
  const tags = entity.metadata.tags ?? [];
  return (
    <InfoCard title="Description">
      <Typography
        variant="body1"
        color={entity.metadata.description ? 'textPrimary' : 'textSecondary'}
      >
        {entity.metadata.description ?? 'No description'}
      </Typography>
      {tags.length > 0 && (
        <div
          style={{
            marginTop: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            flexWrap: 'wrap',
          }}
        >
          <Typography variant="body2" color="textSecondary" component="span">
            Tags
          </Typography>
          {tags.map(tag => (
            <Chip key={tag} label={tag} size="small" style={{ margin: 0 }} />
          ))}
        </div>
      )}
    </InfoCard>
  );
}
