# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

COPY package*.json ./

RUN npm ci

COPY . .

# Create React App inlines REACT_APP_* variables into the static JS
# bundle at BUILD time, not read at runtime - so this must be a build
# ARG, passed via `docker build --build-arg REACT_APP_API_URL=...` or,
# on Railway, the service's "Build Variables" (a separate section from
# the regular runtime Variables tab - see INSTALLATION.md).
ARG REACT_APP_API_URL
ENV REACT_APP_API_URL=$REACT_APP_API_URL

RUN npm run build

# Production stage
FROM node:18-alpine

WORKDIR /app

# Install serve to run production build
RUN npm install -g serve

# Copy built application from builder
COPY --from=builder /app/build ./build

# Railway (and most PaaS) inject a dynamic $PORT at container start, a
# different value on every deploy - this default of 3000 only applies to
# a plain `docker run` with no -e PORT=... set (e.g. local testing).
ENV PORT=3000
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD node -e "require('http').get('http://localhost:' + (process.env.PORT || 3000), (r) => { if (r.statusCode !== 200) process.exit(1) }).on('error', () => process.exit(1))"

# Shell form (not a JSON array) so $PORT is expanded by the shell at
# container start, not baked in at build time.
CMD serve -s build -l $PORT
