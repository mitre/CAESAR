#!/bin/bash
set -e 

# Function to display script usage
usage() {
    echo "Usage: $0 [-q]"
    echo "Options:"
    echo "  -q: Quiet mode. suppress all interactive prompts"
    exit 1
}

# Parse command line options
while getopts ":q" opt; do
    case ${opt} in
        q)
            quiet=true
            ;;
        \?)
            echo "Invalid option: $OPTARG" 1>&2
            usage
            ;;
        :)
            echo "Option -$OPTARG requires an argument." 1>&2
            usage
            ;;
    esac
done
shift $((OPTIND -1))


echo "Installing MITRE Certificates"
sudo wget -q -O - --no-check-certificate https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/os_scripts/install_certs.sh | sudo sh

echo "Updating Packages..."
sudo apt-get update && sudo apt-get upgrade -y

# Check if psql is installed
if ! command -v psql &> /dev/null
then
    echo "psql is not installed. Installing..."
    sudo apt-get install postgresql-client -y
else
    echo "psql is already installed."
fi

# Add the psqlc alias to the user's bash configuration file
echo "alias psqlc='psql -U postgres -h localhost bayanat'" >> ~/.bashrc
# Apply the changes immediately
source ~/.bashrc

# sudo apt-get install -y \
#                 exiftool \
#                 libpq-dev \
#                 build-essential \
#                 python3-dev \
#                 python3-virtualenv \
#                 libzip-dev \
#                 libxml2-dev \
#                 libssl-dev \
#                 libffi-dev \
#                 libxslt1-dev \
#                 libncurses5-dev \
#                 python-setuptools \
#                 postgresql \
#                 postgresql-contrib \
#                 python3-pip \
#                 libpq-dev \
#                 git \
#                 redis-server \
#                 libimage-exiftool-perl \
#                 postgis \
#                 ffmpeg \
#                 tesseract-ocr

npm install --save-dev --save-exact prettier

env_file="./.env"
dev_env_file="./.devcontainer/.env-devcontainer"
current_datetime=$(date +"%Y%m%d_%H%M%S")
pgdata="./pgdata"

# replace the dotenv file with the one for the devcontanier (backup the original)
if [ -f "$env_file" ]; then
    mv "$env_file" "${env_file}_${current_datetime}.backup"
fi
cp "$dev_env_file" "$env_file"

sudo mkdir -p $pgdata
sudo chown -R vscode $pgdata

# If -quiet option is not specified, prompt the user to start docker containers
if [ -z "$quiet" ]; then
    read -t 30 -p "Do you want to start the CAESAR docker containers? (y/N): " start
    if [[ $start == "y" || $start == "Y" ]]; then
        docker compose up -d --build
        echo
    elif [ -z "$start" ]; then
        echo 
        echo 'To start CAESAR, enter "docker compose up -d"'
    fi
else
    # bring up docker containers here...
    docker compose up -d --build
fi