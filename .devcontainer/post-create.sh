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
sudo apt-get update && sudo apt-get upgrade

# Check if psql is installed
if ! command -v psql &> /dev/null
then
    echo "psql is not installed. Installing..."
    sudo apt-get install postgresql-client -y
else
    echo "psql is already installed."
fi

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

# Add the psqlc alias to the user's bash configuration file
echo "alias psqlc='psql -U postgres -h localhost bayanat'" >> ~/.bashrc
# Apply the changes immediately
source ~/.bashrc

# Define the template file and output file and default vars
template_file=".devcontainer/.env-template"
output_file=".devcontainer/.env-devcontainer"
password="change-me"
encoded_passphrase="oITuL697Y25v9vT9F362LjWk"

# If -quiet option is not specified, prompt the user for password
if [ -z "$quiet" ]; then
    # Prompt the user for the option with a timeout of 10 seconds
    read -t 10 -p "Do you want to enter a password manually? (y/N): " option
    if [[ $option == "y" || $option == "Y" ]]; then
        # If user chooses to enter a password manually
        read -s -p "Enter your password: " passphrase
        echo
        password=$passphrase
    elif [ -z "$option" ]; then 
        echo
    fi
fi 

# If -quiet option is not specified, prompt the user for secret option
if [ -z "$quiet" ]; then
    read -t 10 -p "Generate a base64 encoded random secret? (y/N): " gen
    if [[ $gen == "y" || $gen == "Y" ]]; then
        # randomly generate a passphrase/secret
        encoded_passphrase=$(openssl rand -base64 32)
        echo "generated base64 encoded random secret"
    elif [ -z "$gen" ]; then 
        echo
    fi
fi

# Check if template file exists
# if [ ! -f "$template_file" ]; then
#     echo "Template file not found: $template_file. $output_file not written so don't forget to create one manually."
# else
#     cp "$template_file" "$output_file"
#     # Replace the {{SECRET}} placeholder with the generated passphrase
#     sed -i "s:{{SECRET}}:$encoded_passphrase:g" "$output_file"
#     # Replace the {{PASSWORD}} placeholder with the password
#     sed -i "s:{{PASSWORD}}:$password:g" "$output_file"  
#     echo "Passwords and secrets replaced successfully. Output written to $output_file."
# fi

# If -quiet option is not specified, prompt the user to start docker containers
if [ -z "$quiet" ]; then
    read -t 30 -p "Do you want to start the CAESAR docker containers? (y/N): " start
    if [[ $start == "y" || $start == "Y" ]]; then
        docker compose --env-file .devcontainer/.env-devcontainer -f docker-compose.yml -f .devcontainer/docker-compose-devcontainer.yml up -d --build
        echo
    elif [ -z "$start" ]; then
        echo 
        echo 'To start CAESAR, enter "docker compose up -d"'
    fi
else
    # bring up docker containers here...
    docker compose --env-file .devcontainer/.env-devcontainer -f docker-compose.yml -f .devcontainer/docker-compose-devcontainer.yml up -d --build
fi
