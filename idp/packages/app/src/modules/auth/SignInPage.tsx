import React from 'react';
import { SignInPage } from '@backstage/core-components';
import { SignInPageBlueprint } from '@backstage/plugin-app-react';
import { googleAuthApiRef } from '@backstage/frontend-plugin-api';
import { createFrontendModule } from '@backstage/frontend-plugin-api';
import type { SignInPageProps } from '@backstage/plugin-app-react';

// Override the default sign-in-page:app extension (no name = same ID as the default)
const signInPageExtension = SignInPageBlueprint.make({
  params: {
    loader: async () => {
      const Component = (props: SignInPageProps) =>
        React.createElement(SignInPage, {
          ...props,
          providers: [
            'guest',
            {
              id: 'google-auth-provider',
              title: 'Google',
              message: 'Sign in with your Google account',
              apiRef: googleAuthApiRef,
            },
          ],
        });
      return Component;
    },
  },
});

export const authModule = createFrontendModule({
  pluginId: 'app',
  extensions: [signInPageExtension],
});
