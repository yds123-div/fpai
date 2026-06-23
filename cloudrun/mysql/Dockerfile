FROM mysql:8.0

ENV MYSQL_DATABASE=fpai \
    TZ=Asia/Shanghai

COPY init.sql /docker-entrypoint-initdb.d/

EXPOSE 3306
