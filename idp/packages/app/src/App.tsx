import { createApp } from '@backstage/frontend-defaults';
import catalogPlugin from '@backstage/plugin-catalog/alpha';
import { navModule } from './modules/nav';
import { blueThemeModule } from './themes/blueTheme';
import { authModule } from './modules/auth/SignInPage';

export default createApp({
  features: [catalogPlugin, navModule, blueThemeModule, authModule],
});
