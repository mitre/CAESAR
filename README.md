<p align="left">
    <img alt="CAESAR" width="500" src="enferno/static/img/logo.png">
</p>

## Getting Started

CAESAR runs as a set of Docker containers using the `docker compose` command.

1. Clone the repository and change to the caesar directory
    ```bash
    git clone git@gitlab.mitre.org:dokazy/caesar.git
    cd caesar
    ```

2. Copy the `.env-sample` file and change the values as appropriate. You should probably change all of the values that are set to `change-me`.
    ```bash
    cp .env-sample .env
    ```

3. Bring the system up
    ```bash
    docker compose up -d
    ```

4. Wait about a minute for the server to start up and then access the website at http://localhost:5000

5. Admin login credentials for the website are set in the .env file.

## Configuring the System

Initially, CAESAR is configured by changing values in the `.env` file located at the root of the project. Once the application is running and the configuration is changed through the UI, a `config.json` file will be created. The settings in `config.json` will override the values in the `.env` file so changes to the configuration should be done using the UI where possible. There are some configurations, namely the Docker-specific ones, that are only set in the `.env` file. 

## Caesar Data

### Locations:

- At first startup, or when the `location` table of the database is empty on startup, the locations are set using a file located in the `./enferno/data/` directory
- You can change which file is used by setting the filename as the `LOCATIONS_FILENAME` value in the `.env` file
- There are 2 location files currently in the `./enferno/data/` directory that you can use
  - `LOCATIONS_FILENAME=ukraine_locations.csv` is a list of locations in Ukraine that was pulled from https://data.humdata.org/dataset/cod-ab-ukr
  - `LOCATIONS_FILENAME=sudan_locations.csv` is a list of locations in Sudan that was pulled from https://data.humdata.org/dataset/cod-ab-sdn
- You can use a custom set of locations by creating a new CSV file that follows the same format as the existing locations files, adding the file to `./enferno/data/` and setting the `LOCATIONS_FILENAME` variable in the `.env` file

## Development

### API Documentation

CAESAR includes API documentation that is available at `/api/docs/` when CAESAR is deployed with a `dev` configuration. When running with a `dev` configuration, you can navigate to it by opening http://localhost:5000/api/docs/ in your browser. CAESAR can be set with either a `dev` or `prod` configuration in the `.env` file.

### Database Migrations

If you need to change the database model, you will need to create a migration to ensure the changes are reflected in the existing databases. 

#### Create and Execute a Migration

1. Make the changes to the model
2. Create a new migration file with the command `flask db migrate -m "Add a short description here"`
3. Verify the new migration file in the `migrations/versions/` directory
4. Execute the migration with the command `flask db upgrade`
5. Commit the new migration file

#### Rolling Back a Migration

If something goes wrong with the new migration and you need to undo it, run `flask db downgrade`

### Updating Translation Files

Caesar translation uses the Flask-Babel library. A messages.pot file holds all default english messages, while messages.po language catalog file holds translations for different languages.
The babel command line tools can be used to generate/regenerate message files, though it is necessary to add translations for new text to these files. Regenerating messages files should be done for any wholesale changes or additions of text messages to Caesar.
See https://babel.pocoo.org/en/latest/cmdline.html
To generate a new messages.pot file (caesar/messages.pot) based on code changes using the gettext() conventions, run `pybabel extract -F babel.cfg -o messages.pot .` from the project root
To generate new messages.po catalog files from the messages.pot file, run `pybabel update -i messages.pot -d ./enferno/translations/` from the project root
 * messages.po catalog files updated in this way should port all old translations
 * new translations should be added to the messages.po files
To generate new messages.mo files from the messages.po files, run `pybabel compile -d ./enferno/translations/` from the project root
messages.pot, messages.po, and messages.mo files should all show changes in source control diffs

## Deploying with an External Database

There is an alternative Docker Compose file available if deploying with an external PostgreSQL database, such as Amazon Relational Database Service (RDS). The `docker-compose-co.yml` file overrides the default `docker-compose.yml` file to enable running the PostgreSQL server external to the other containers. Make sure the `POSTGRES_HOST`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` variables are set in the `.env` file and then run `docker compose -f docker-compose.yml -f docker-compose.co.yml up -d`. If your PostgreSQL runs on a non-standard port, include that in the POSTRES_HOST field. There is also a utility script that you can use to run Docker Compose commands with the configuration files already set. You can run Docker Compose commands by running `bash bin/co-compose.sh` followed by the relevant Docker Compose command. For example, `bash bin/co-compose.sh logs bayanat` would display the logs for the main web server.

## Deploy a PgAdmin Container
PgAdmin is a tool for interacting with the CAESAR postgres database. To view the CAESAR database from PgAdmin running in a container, run `docker compose up -d pgadmin`.  

## CAESAR History

The CAESAR system was adapted from [Bayanat](https://www.bayanat.org/), specifically v1.29. 

### Major Changes from Bayanat v1.29

- Renames bulletins to primary records
- Renames incidents to investigations
- Adds a top-level data type for organizations
- Adds a map to events and the ability to add custom locations
- Adds the ability to draw polygon, line, and point based locations
- Uses MapLibre front-end mapping plugin instead of Leaflet
- Adds a universal search capability that searches across the major data types
- Makes the OpenID Connect authentication generic instead of Google-specific
- Changes to the Docker Compose configuration
- Primary Records
  - Adds the ability to upload and visualize shapefiles
  - Adds the ability to track authors
  - Adds a field for `Discovery File Name`
  - Adds a field for tracking the consented uses
  - Adds a checkbox to indicate the translation in the record is verified
- Actors
  - Adds a credibility field
  - Changes the `Nickname` field to `Alias` and allows for multiple aliases
  - Adds a field for tracking social media accounts
  - Adds a field for tracking sanction regimes
  - Renames `Events` to `Locations of Reported Activity`
- Adds a `Graphic` checkbox to media that blurs previews by default
- Auto loads locations based on a specified file; Ukraine and Sudan location files included by default
- Adds a capability to import Zotero records
