#!/bin/bash
set -e
echo "=== FPAI Boot ==="

# 启动 MariaDB 并初始化
echo "[init] Starting MariaDB for setup..."
mysqld --user=mysql --bind-address=127.0.0.1 --skip-grant-tables &
MYSQL_PID=$!

for i in $(seq 1 30); do
    if mysqladmin ping -h 127.0.0.1 --silent 2>/dev/null; then break; fi
    sleep 2
done

echo "[init] Creating fpai database and user..."
mysql -h 127.0.0.1 -u root <<'EOSQL'
FLUSH PRIVILEGES;
CREATE DATABASE IF NOT EXISTS fpai DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'fpai'@'127.0.0.1' IDENTIFIED BY 'fpai_cloudbase_2024';
CREATE USER IF NOT EXISTS 'fpai'@'localhost' IDENTIFIED BY 'fpai_cloudbase_2024';
GRANT ALL PRIVILEGES ON fpai.* TO 'fpai'@'127.0.0.1';
GRANT ALL PRIVILEGES ON fpai.* TO 'fpai'@'localhost';
FLUSH PRIVILEGES;
EOSQL

if [ -f /docker-entrypoint-initdb.d/init.sql ]; then
    echo "[init] Running init.sql..."
    mysql -h 127.0.0.1 -u root fpai < /docker-entrypoint-initdb.d/init.sql 2>/dev/null || true
    echo "[init] Done."
fi

echo "[init] Stopping temp MariaDB..."
kill $MYSQL_PID 2>/dev/null || true
sleep 2

echo "[init] Starting supervisord..."
exec supervisord -c /etc/supervisor/conf.d/supervisord.conf
