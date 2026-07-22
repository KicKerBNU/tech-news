FROM node:20-bookworm-slim

RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-pip git \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY agent/requirements.txt /tmp/agent-requirements.txt
RUN pip3 install --break-system-packages --no-cache-dir -r /tmp/agent-requirements.txt

COPY backend/package.json backend/yarn.lock backend/
WORKDIR /app/backend
RUN corepack enable && yarn install --frozen-lockfile

WORKDIR /app
RUN mkdir -p /app/repo
COPY backend backend/

ENV REPO_ROOT=/app/repo
ENV NODE_ENV=production

WORKDIR /app/backend
EXPOSE 3000
CMD ["yarn", "start"]
