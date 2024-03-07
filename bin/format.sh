#!/bin/bash

run_djlint_from_host() {
  echo "Running djlint/djhtml from host..."
  docker exec $1 sh -c "djlint . --reformat --format-js --format-css ; djhtml ."
}

run_djlint_direct() {
  echo "Running djlint/djhtml directly..."
  djlint . --reformat --format-js --format-css ; djhtml .
}

echo "Running Prettier..."
npm run format

read -p "Enter your docker container name or press enter to run directly: " container_name
if [ -z "$container_name" ]; then
  run_djlint_direct
else
  run_djlint_from_host $container_name
fi

echo "Formatting complete."
