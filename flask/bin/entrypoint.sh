#!/bin/sh
set -e

ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD=$ADMIN_PASSWORD

if [ "$ROLE" = "flask" ]; then
  echo ":: Creating Bayanat Database ::"
  flask create-db --create-exts
  echo ":: Trying to import default data ::"
  flask import-data
  echo ":: Running Available Database Migrations ::"
  flask db upgrade
  echo ":: Trying to Create Admin User ::"
  flask install --username ${ADMIN_USERNAME:-postgres} --password ${ADMIN_PASSWORD:-change_this_password}
  echo ":: Starting Bayanat ::"
  if [ "$FLASK_DEBUG" = "1" ]; then
    echo ":: Running Bayanat in Debug Mode ::"
    exec uwsgi --http 0.0.0.0:5000 --protocol uwsgi --master --enable-threads --threads 2  --processes 1 --py-autoreload 1 --wsgi  run:app
  else
    exec uwsgi --http 0.0.0.0:5000 --protocol uwsgi --master --enable-threads --threads 2  --processes 1 --wsgi run:app
  fi

elif [ "$ROLE" = "celery" ]; then
  echo ":: Starting Celery for Bayanat ::"
  exec celery -A enferno.tasks worker --autoscale 1,5 -l error -B -s /tmp/celerybeat-schedule
fi

