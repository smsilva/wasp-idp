FROM node:24-slim

ENV NODE_ENV=production

WORKDIR /srv

COPY package.json package-lock.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY src/ src/

# The version and commit the home page shows; platform-build.yaml passes them.
ARG APP_VERSION=dev
ARG APP_COMMIT=unknown
ENV APP_VERSION=${APP_VERSION} \
    APP_COMMIT=${APP_COMMIT} \
    PORT=${{ values.port }}

USER 10001

EXPOSE ${{ values.port }}

CMD ["node", "src/server.js"]
