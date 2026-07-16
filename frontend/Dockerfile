# syntax=docker/dockerfile:1.7

FROM node:20-alpine AS builder

WORKDIR /app

COPY . .

RUN if [ -f package-lock.json ] || [ -f npm-shrinkwrap.json ]; then \
      npm ci --no-audit --no-fund; \
    elif [ -f package.json ]; then \
      npm install --no-audit --no-fund; \
    else \
      mkdir -p /app/dist; \
    fi

RUN if [ -f package.json ]; then \
      if npm run | grep -q " build"; then npm run build; else mkdir -p /app/dist && cp -r /app/* /app/dist; fi; \
    else \
      cp -r /app/* /app/dist; \
    fi

FROM node:20-alpine AS runtime

ENV NODE_ENV=production \
    FRONTEND_PORT=3000

WORKDIR /app

RUN npm install -g serve@14.2.3 --no-audit --no-fund \
    && addgroup -S appgroup \
    && adduser -S appuser -G appgroup

COPY --from=builder /app/dist ./dist

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 CMD wget -qO- "http://127.0.0.1:${FRONTEND_PORT}/" >/dev/null || exit 1

CMD ["sh", "-c", "serve -s dist -l ${FRONTEND_PORT}"]
