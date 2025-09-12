#!/bin/bash

# Installation script for Smart Display Cast Manager
# For Raspberry Pi Zero W

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

INSTALL_DIR="/opt/smart-display"

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE} Smart Display Cast Manager     ${NC}"
echo -e "${BLUE} Installation Script            ${NC}"
echo -e "${BLUE}================================${NC}"
echo
echo -e "${YELLOW}Installing to: ${INSTALL_DIR}${NC}"
echo

# Update system
echo -e "${YELLOW}Updating system packages...${NC}"
sudo apt update && sudo apt upgrade -y

# Install required packages
echo -e "${YELLOW}Installing required packages...${NC}"
sudo apt install -y \
    python3 \
    pipx \
    curl \
    nmap \
    avahi-utils \
    net-tools

# Install CATT Python package
echo -e "${YELLOW}Installing CATT (Cast All The Things)...${NC}"
pipx install catt

# Install Docker if not present
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}Installing Docker...${NC}"
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    
    # Enable Docker to start on boot
    sudo systemctl enable docker
    
    echo -e "${GREEN}Docker installed successfully${NC}"
    echo -e "${YELLOW}Please reboot and run this script again to complete setup${NC}"
    
    rm get-docker.sh
    exit 0
else
    echo -e "${GREEN}Docker already installed${NC}"
fi

# Create installation directory and set permissions
echo -e "${YELLOW}Setting up installation directory...${NC}"
sudo mkdir -p ${INSTALL_DIR}
sudo chown $USER:$USER ${INSTALL_DIR}

# Copy files to installation directory
echo -e "${YELLOW}Copying files to ${INSTALL_DIR}...${NC}"
cp -r . ${INSTALL_DIR}/
cd ${INSTALL_DIR}

# Create src directory and move files if needed
mkdir -p src
if [ -f "index.html" ] && [ ! -f "src/index.html" ]; then
    mv index.html src/
    echo -e "${GREEN}Moved index.html to src/${NC}"
fi

# Make scripts executable
chmod +x cast-manager.py

# Create systemd service for auto-start
echo -e "${YELLOW}Creating systemd service...${NC}"
sudo tee /etc/systemd/system/cast-manager.service > /dev/null <<EOF
[Unit]
Description=Smart Display Cast Manager
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/cast-manager.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable cast-manager.service

# Pre-pull Docker images
echo -e "${YELLOW}Pre-pulling Docker images...${NC}"
docker pull httpd:alpine

# Verify CATT installation
echo -e "${YELLOW}Verifying CATT installation...${NC}"
if catt --help &> /dev/null; then
    echo -e "${GREEN}CATT installed successfully${NC}"
else
    echo -e "${RED}CATT installation failed${NC}"
    exit 1
fi

echo
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN} Installation Complete!         ${NC}"
echo -e "${GREEN}================================${NC}"
echo
echo -e "${YELLOW}Installation directory: ${INSTALL_DIR}${NC}"
echo
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Ensure your website files are in '${INSTALL_DIR}/src/' directory"
echo "2. Start the service: sudo systemctl start cast-manager"
echo "3. Check status: sudo systemctl status cast-manager"
echo "4. View logs: sudo journalctl -u cast-manager -f"
echo
echo -e "${YELLOW}The service will automatically:${NC}"
echo "• Scan for your Nest Hub on the network"
echo "• Start a web server serving your content"
echo "• Cast to the Nest Hub when found"
echo "• Start automatically on boot"
echo
echo -e "${BLUE}Service Commands:${NC}"
echo "Start:   sudo systemctl start cast-manager"
echo "Stop:    sudo systemctl stop cast-manager"
echo "Status:  sudo systemctl status cast-manager"
echo "Logs:    sudo journalctl -u cast-manager -f"
echo "Disable: sudo systemctl disable cast-manager"
echo
echo -e "${BLUE}File Locations:${NC}"
echo "Installation: ${INSTALL_DIR}"
echo "Website files: ${INSTALL_DIR}/src/"
echo "Logs: /var/log/cast-manager.log"
echo "Service: /etc/systemd/system/cast-manager.service"
echo
