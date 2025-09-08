#!/bin/bash

# Smart Display Cast Manager Startup Script
# For Raspberry Pi Zero W

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Smart Display Cast Manager...${NC}"

# Check if running as root (required for some network operations)
if [[ $EUID -eq 0 ]]; then
   echo -e "${YELLOW}Warning: Running as root${NC}"
fi

# Check if Docker is installed and running
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker first:"
    echo "curl -fsSL https://get.docker.com -o get-docker.sh"
    echo "sudo sh get-docker.sh"
    echo "sudo usermod -aG docker \$USER"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${YELLOW}Starting Docker daemon...${NC}"
    sudo systemctl start docker
    sleep 3
fi

# Check if Python3 is available
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python3 is not installed${NC}"
    echo "Please install Python3: sudo apt update && sudo apt install python3"
    exit 1
fi

# Create logs directory
sudo mkdir -p /var/log
sudo touch /var/log/cast-manager.log
sudo chmod 666 /var/log/cast-manager.log

# Pull required Docker images
echo -e "${YELLOW}Pulling required Docker images...${NC}"
docker pull httpd:alpine
docker pull ryanbarrett/catt-chromecast

# Make sure the script is executable
chmod +x cast-manager.py

# Create src directory if it doesn't exist
if [ ! -d "src" ]; then
    echo -e "${YELLOW}Creating src directory...${NC}"
    mkdir -p src
    
    # If index.html exists in current directory, move it to src
    if [ -f "index.html" ]; then
        mv index.html src/
        echo "Moved index.html to src/"
    fi
fi

# Check if we have content to serve
if [ ! -f "src/index.html" ]; then
    echo -e "${RED}Error: No index.html found in src/ directory${NC}"
    echo "Please ensure your website files are in the src/ directory"
    exit 1
fi

echo -e "${GREEN}Starting Cast Manager...${NC}"
echo "Press Ctrl+C to stop"
echo "Logs will be written to /var/log/cast-manager.log"
echo

# Run the cast manager
python3 cast-manager.py
