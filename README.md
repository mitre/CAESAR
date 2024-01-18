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
    cp .env-sample.env
    ```

3. Bring the system up
    ```bash
    docker compose up -d
    ```

4. Access the website at http://localhost:5000


## Updating Translation Files

Caesar translation uses the Flask-Babel library. A messages.pot file holds all default english messages, while messeages.po language catalog file hold translations for different languages.
We need to provide translations for our text, but the babel command line tools can be used to generate/regenerate message files. This should be done for any wholesale changes or additions of text messages to Caesar.
See https://babel.pocoo.org/en/latest/cmdline.html
To generate a new messages.pot file (caesar/messages.pot) based on code changes using the gettext() conventions, run < pybabel extract -F babel.cfg -o messages.pot . > from the project root
To generate new messages.po catalog files from the messages.pot file, run < pybabel update -i messages.pot -d .\enferno\translations\ > from the project root
 * messages.po catalog files updated in this way should port all old translations
 * new translations should be added to the messages.po files
To generate new messages.mo files from the messages.po files, run < pybabel compile -d .\enferno\translations\ > from the project root
messages.pot, messages.po, and messages.mo files should all show changes in source control diffs 


## Caesar Data

Location data has been added to the default bayanat data set at /enferno/data in a Locations.csv file. This file contains a list of Ukrainian cities that was pulled from https://simplemaps.com/data/ua-cities.
