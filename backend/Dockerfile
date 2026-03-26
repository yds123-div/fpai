FROM python:3.11-slim

WORKDIR /app/backend

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    HOST=0.0.0.0

# bcrypt 等依赖可能需要编译工具链
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential gcc \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端源码（不包含 .dockerignore 里排除的敏感文件）
COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host ${HOST} --port ${PORT}"]
