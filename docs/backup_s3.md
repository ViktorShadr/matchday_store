# Резервные копии в Timeweb S3

## Назначение

Система резервного копирования хранит копии PostgreSQL и media-файлов в Timeweb Object Storage (S3), чтобы потеря основного сервера не приводила к потере данных проекта.

Текущая инфраструктура:

```text
Production Server
├── PostgreSQL (Docker)
├── Django (Docker)
├── Media files (Docker Volume)
└── Backup scripts

            │

            ▼

Timeweb Object Storage (S3)
├── PostgreSQL backups
└── Media backups
```

---

## Структура проекта

На сервере используются следующие пути:

```text
/opt/matchday_store/
├── docker-compose.prod.yml
├── .env
└── ops
    ├── backup
    │   ├── s3_backup.sh
    │   ├── s3_backup.env
    │   └── logs
    └── db
        └── restore_verify.sh
```

---

## Политика хранения

### PostgreSQL

```text
backups/postgres/daily/
backups/postgres/weekly/
backups/postgres/monthly/
```

### Media

```text
backups/media/daily/
backups/media/weekly/
backups/media/monthly/
```

### Retention

| Тип     | Срок хранения |
| ------- | ------------- |
| daily   | 14 дней       |
| weekly  | 8 недель      |
| monthly | 6 месяцев     |

Удаление старых объектов происходит автоматически после успешной загрузки новых резервных копий.

---

## Настройка Timeweb Object Storage

Параметры текущего бакета:

```text
Endpoint: https://s3.twcstorage.ru
Bucket: 726511e9-10a5-4c9e-9041-c1c53f1a97d6
Region: ru-1
```

Для работы необходимо создать:

* Access Key
* Secret Key

Минимальные права:

* ListBucket
* GetObject
* PutObject
* DeleteObject

Никогда не хранить ключи:

* в Git
* в документации
* в issue tracker
* в публичных чатах

---

## Установка AWS CLI v2

На Ubuntu 24.04 рекомендуется использовать официальный AWS CLI v2.

```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "/tmp/awscliv2.zip"

unzip /tmp/awscliv2.zip -d /tmp

sudo /tmp/aws/install

aws --version
```

Проверка:

```bash
aws --version
```

Ожидаемый результат:

```text
aws-cli/2.x.x
```

---

## Конфигурация

Файл:

```text
/opt/matchday_store/ops/backup/s3_backup.env
```

Права:

```bash
chmod 600 /opt/matchday_store/ops/backup/s3_backup.env
```

Пример содержимого:

```env
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

S3_BUCKET_NAME=726511e9-10a5-4c9e-9041-c1c53f1a97d6
S3_ENDPOINT_URL=https://s3.twcstorage.ru
S3_REGION=ru-1

COMPOSE_FILE=/opt/matchday_store/docker-compose.prod.yml

DB_NAME=matchday_store
DB_USER=...
DB_PASSWORD=...

POSTGRES_SERVICE=db

MEDIA_SOURCE=container
MEDIA_SERVICE=web
MEDIA_PATH=/app/media
```

---

## Ручной запуск резервного копирования

### Daily

```bash
cd /opt/matchday_store/ops/backup

./s3_backup.sh daily
```

### Weekly

```bash
./s3_backup.sh weekly
```

### Monthly

```bash
./s3_backup.sh monthly
```

После успешного выполнения:

* архив PostgreSQL загружается в S3;
* архив media загружается в S3;
* старые объекты удаляются по retention policy;
* временные файлы удаляются автоматически.

---

## Проверка содержимого S3

Подгружаем переменные:

```bash
set -a
. /opt/matchday_store/ops/backup/s3_backup.env
set +a
```

Проверяем PostgreSQL backups:

```bash
aws \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  s3 ls "s3://$S3_BUCKET_NAME/backups/postgres/daily/"
```

Проверяем media backups:

```bash
aws \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  s3 ls "s3://$S3_BUCKET_NAME/backups/media/daily/"
```

---

## Автоматический запуск через Cron

Текущая конфигурация:

```cron
# Ежедневный бэкап
0 2 * * * /opt/matchday_store/ops/backup/s3_backup.sh daily >> /opt/matchday_store/ops/backup/logs/daily.log 2>&1

# Еженедельный бэкап
0 3 * * 0 /opt/matchday_store/ops/backup/s3_backup.sh weekly >> /opt/matchday_store/ops/backup/logs/weekly.log 2>&1

# Ежемесячный бэкап
0 4 1 * * /opt/matchday_store/ops/backup/s3_backup.sh monthly >> /opt/matchday_store/ops/backup/logs/monthly.log 2>&1
```

Проверить cron:

```bash
crontab -l
```

Проверить сервис:

```bash
systemctl status cron
```

Ожидаемый статус:

```text
Active: active (running)
```

Cron автоматически запускается после перезагрузки сервера.

---

## Проверка восстановления PostgreSQL

Скачиваем резервную копию:

```bash
aws \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  s3 cp \
  "s3://$S3_BUCKET_NAME/backups/postgres/daily/<backup>.sql.gz" \
  /tmp/matchday_postgres.sql.gz
```

Проверяем восстановление без риска для production:

```bash
COMPOSE_FILE=/opt/matchday_store/docker-compose.prod.yml \
/opt/matchday_store/ops/db/restore_verify.sh \
/tmp/matchday_postgres.sql.gz
```

Скрипт:

1. Создает временную БД.
2. Восстанавливает туда дамп.
3. Проверяет таблицу `django_migrations`.
4. Удаляет временную БД.

Production-база при этом не изменяется.

---

## Полное восстановление PostgreSQL

⚠️ Выполнять только на новом сервере или во время maintenance window.

Остановка сервисов:

```bash
docker compose -f /opt/matchday_store/docker-compose.prod.yml stop nginx web worker email-worker beat
```

Пересоздание БД:

```bash
docker compose -f /opt/matchday_store/docker-compose.prod.yml exec -T db sh -c '
dropdb -U "$DB_USER" --if-exists "$DB_NAME"
createdb -U "$DB_USER" "$DB_NAME"
'
```

Восстановление:

```bash
gunzip -c /tmp/matchday_postgres.sql.gz | \
docker compose -f /opt/matchday_store/docker-compose.prod.yml exec -T db sh -c '
psql -v ON_ERROR_STOP=1 -U "$DB_USER" "$DB_NAME"
'
```

Запуск сервисов:

```bash
docker compose -f /opt/matchday_store/docker-compose.prod.yml up -d
```

---

## Восстановление Media

Скачивание:

```bash
aws \
  --endpoint-url "$S3_ENDPOINT_URL" \
  --region "$S3_REGION" \
  s3 cp \
  "s3://$S3_BUCKET_NAME/backups/media/daily/<backup>.tar.gz" \
  /tmp/matchday_media.tar.gz
```

Остановка сервисов:

```bash
docker compose -f /opt/matchday_store/docker-compose.prod.yml stop nginx worker email-worker
```

Восстановление:

```bash
cat /tmp/matchday_media.tar.gz | \
docker compose -f /opt/matchday_store/docker-compose.prod.yml exec -T web sh -c '
mkdir -p /app/media
find /app/media -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
tar -xzf - -C /app
'
```

Запуск:

```bash
docker compose -f /opt/matchday_store/docker-compose.prod.yml up -d
```

---

## Рекомендуемый регламент

Ежеквартально:

1. Скачать резервную копию из S3.
2. Выполнить `restore_verify.sh`.
3. Проверить открытие сайта.
4. Проверить наличие media-файлов.

Резервная копия считается рабочей только после успешной проверки восстановления.

Главный принцип:

> Backup, который ни разу не проверяли восстановлением, нельзя считать резервной копией.
