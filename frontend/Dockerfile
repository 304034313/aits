# 版本基准：tools/installers/versions.json → docker.nodejs_image / nginx_image
# 全局 ARG：多阶段构建时供各 FROM 使用（compose build.args 可覆盖）
ARG NODE_IMAGE=node:24.16.0-bookworm
ARG NGINX_IMAGE=nginx:1.27-alpine
ARG VITE_AITS_PACK_PROFILE=

FROM ${NODE_IMAGE} AS build

ARG VITE_AITS_PACK_PROFILE=
ENV VITE_AITS_PACK_PROFILE=$VITE_AITS_PACK_PROFILE

WORKDIR /app

COPY package.json package-lock.json* docker-npm-install.sh ./
RUN chmod +x docker-npm-install.sh && ./docker-npm-install.sh

COPY . .
RUN npm run build

FROM ${NGINX_IMAGE}

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
