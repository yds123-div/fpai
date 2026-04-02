FROM node:20-alpine AS build

WORKDIR /app/frontend

# 先复制 package 文件，利用 Docker 缓存
COPY package.json ./

# 安装依赖
RUN npm install

# 复制源码并构建
COPY . .
RUN npm run build

FROM nginx:1.27-alpine

WORKDIR /usr/share/nginx/html

# 从构建阶段复制产物
COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
