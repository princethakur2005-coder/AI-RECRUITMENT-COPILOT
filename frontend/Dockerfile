# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS builder

ARG API_BASE_URL=http://backend:8000

WORKDIR /app

COPY package*.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN mkdir -p public
RUN API_BASE_URL=${API_BASE_URL} npm run build

FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    FRONTEND_PORT=3000

WORKDIR /app

RUN addgroup -S appgroup \
    && adduser -S appuser -G appgroup

COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/package-lock.json ./package-lock.json
RUN npm ci --production --no-audit --no-fund

COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD wget -qO- "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null || exit 1

CMD ["sh", "-c", "npx next start -p ${FRONTEND_PORT:-3000}"]
