import { createBackendModule } from '@backstage/backend-plugin-api';
import {
  authProvidersExtensionPoint,
  createOAuthProviderFactory,
} from '@backstage/plugin-auth-node';
import {
  googleAuthenticator,
  googleSignInResolvers,
} from '@backstage/plugin-auth-backend-module-google-provider';

export default createBackendModule({
  pluginId: 'auth',
  moduleId: 'custom-google-provider',
  register(reg) {
    reg.registerInit({
      deps: { providers: authProvidersExtensionPoint },
      async init({ providers }) {
        providers.registerProvider({
          providerId: 'google',
          factory: createOAuthProviderFactory({
            authenticator: googleAuthenticator,
            signInResolver:
              googleSignInResolvers.emailMatchingUserEntityAnnotation({
                dangerouslyAllowSignInWithoutUserInCatalog: true,
              }),
          }),
        });
      },
    });
  },
});
