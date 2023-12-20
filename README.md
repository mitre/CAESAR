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

## Caesar Data

Location data has been added to the default bayanat data set at /enferno/data in a Locations.csv file. This file contains a list of Ukrainian cities that was pulled from https://simplemaps.com/data/ua-cities.
