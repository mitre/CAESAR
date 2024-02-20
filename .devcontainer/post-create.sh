#!/bin/bash

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


echo "installing MITRE certificates"
sudo wget -q -O - --no-check-certificate https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/os_scripts/install_certs.sh | MODE=alpine sudo sh

echo "installing MITRE certificates for python"
curl -ksSL https://gitlab.mitre.org/mitre-scripts/mitre-pki/raw/master/tool_scripts/install_certs.sh | MODE=python sh

# Check if psql is installed
if ! command -v psql &> /dev/null
then
    echo "psql is not installed. Installing..."
    # Update package lists
    sudo apt-get update
    # Install psql
    sudo apt-get install postgresql-client -y
    echo "psql has been installed successfully."
else
    echo "psql is already installed."
fi

# Add the psqlc alias to the user's bash configuration file
echo "alias psqlc='psql -U postgres -h localhost bayanat'" >> ~/.bashrc
# Apply the changes immediately
source ~/.bashrc

# Define the template file and output file
template_file=".env-template"
output_file=".env"

password="change-me"
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

encoded_passphrase="oITuL697Y25v9vT9F362LjWk"
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
if [ ! -f "$template_file" ]; then
    echo "Template file not found: $template_file. $output_file not written so don't forget to create one manually."
else
    cp "$template_file" "$output_file"
    # Replace the {{SECRET}} placeholder with the generated passphrase
    sed -i "s:{{SECRET}}:$encoded_passphrase:g" "$output_file"
    # Replace the {{PASSWORD}} placeholder with the password
    sed -i "s:{{PASSWORD}}:$password:g" "$output_file"  
    echo "Passwords and secrets replaced successfully. Output written to $output_file."
fi

# If -quiet option is not specified, prompt the user for secret option
if [ -z "$quiet" ]; then
    read -t 30 -p "Do you want to start the CAESAR docker containers? (y/N): " start
    if [[ $start == "y" || $start == "Y" ]]; then
        docker compose up -d
        echo
    elif [ -z "$start" ]; then
        echo 
        echo 'To start CAESAR, enter "docker compose up -d"'
    fi
fi