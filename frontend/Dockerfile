FROM node:20-alpine AS build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
COPY contract/mock_run.json /app/contract/mock_run.json
COPY demo/recorded_runs /app/demo/recorded_runs
COPY demo/field_mosaics /app/demo/field_mosaics

# Leave VITE_API_URL empty when Caddy serves UI and /api on the same hostname.
ARG VITE_API_URL=""
ARG VITE_DEMO_MODE="false"
ENV VITE_API_URL=${VITE_API_URL} \
    VITE_DEMO_MODE=${VITE_DEMO_MODE}

RUN npm run build

FROM nginx:alpine AS runtime

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
