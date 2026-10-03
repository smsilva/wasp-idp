import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import { navModule } from './modules/nav';
import { blueThemeModule } from './themes/blueTheme';
import { authModule } from './modules/auth/SignInPage';
import { entityPresentationModule } from './modules/entityPresentation';
import { entityDependenciesModule } from './modules/entityDependencies';

export default createApp({
  features: [
    catalogPlugin,
    navModule,
    blueThemeModule,
    authModule,
    entityPresentationModule,
    entityDependenciesModule,
  ],
});
