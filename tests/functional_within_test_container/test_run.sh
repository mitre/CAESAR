test_run_project_name="test_run_"`date +"%m_%d_%Y_%H_%M_%S"`

# Start up PostgreSQL and Redis and give them 10 seconds to start running
BAYANAT_EXTERNAL_PORT=5001 POSTGRES_EXTERNAL_PORT=5433 REDIS_EXTERNAL_PORT=6380 docker compose -p $test_run_project_name up -d postgres redis
sleep 10

# Start Bayanat and Celery and give them 10 seconds to start running
BAYANAT_EXTERNAL_PORT=5001 POSTGRES_EXTERNAL_PORT=5433 REDIS_EXTERNAL_PORT=6380 docker compose -p $test_run_project_name up -d celery bayanat
sleep 10

# Install the test-specific requirements
docker compose -p $test_run_project_name exec --user root bayanat pip install -r tests/requirements-test.txt

# Run the tests
docker compose -p $test_run_project_name exec --user root bayanat python -m pytest tests/functional_within_test_container

# Stop and remove the containers
docker compose -p $test_run_project_name down -v
