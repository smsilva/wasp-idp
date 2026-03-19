#!/bin/bash
node_version="v24.14.0"

# Prerequisites
# https://backstage.io/docs/getting-started/#prerequisites

# Installing nvm
# https://github.com/nvm-sh/nvm#install--update-script

curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

nvm ls

nvm install ${node_version?}

nvm alias default ${node_version?}

# Install via npm
npm install --location=global yarn

# Create your Backstage App
# https://backstage.io/docs/getting-started/#create-your-backstage-app

npx @backstage/create-app

# Run the Backstage app
# https://backstage.io/docs/getting-started/#run-the-backstage-app

cd backstage

yarn start

# http://localhost:3000
