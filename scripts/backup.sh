#!/bin/bash
# Automated backup script for GitClone (Database and Repositories)

# Configuration
BACKUP_DIR="./backups"
KEEP_BACKUPS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

echo "Starting backup at $(date)..."

# 1. Back up Postgres Database
echo "Backing up database..."
DB_CONTAINER=$(docker compose ps -q postgres 2>/dev/null)
if [ -n "$DB_CONTAINER" ]; then
    docker exec "$DB_CONTAINER" pg_dump -U gitclone gitclone > "$BACKUP_DIR/db_$TIMESTAMP.sql"
    echo "Database backed up to $BACKUP_DIR/db_$TIMESTAMP.sql"
else
    echo "Warning: Postgres container is not running. Skipping database backup."
fi

# 2. Back up Repositories Volume
echo "Backing up repositories..."
WEB_CONTAINER=$(docker compose ps -q web 2>/dev/null)
if [ -n "$WEB_CONTAINER" ]; then
    docker exec "$WEB_CONTAINER" tar -czf - /repos > "$BACKUP_DIR/repos_$TIMESTAMP.tar.gz"
    echo "Repositories backed up to $BACKUP_DIR/repos_$TIMESTAMP.tar.gz"
else
    echo "Warning: Web container is not running. Skipping repositories backup."
fi

# 3. Clean up old backups (keep only the last N backups)
echo "Cleaning up old backups (keeping last $KEEP_BACKUPS)..."
find "$BACKUP_DIR" -name "db_*.sql" -mtime +$KEEP_BACKUPS -exec rm {} \;
find "$BACKUP_DIR" -name "repos_*.tar.gz" -mtime +$KEEP_BACKUPS -exec rm {} \;

echo "Backup process completed successfully at $(date)!"
