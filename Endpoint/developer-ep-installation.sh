#!/bin/bash

# Update the package lists for upgrades and new package installations
sudo apt-get update

# Install curl, zip, and unzip
sudo apt-get install -y curl zip unzip

#Download microsoft edge deb
wget https://packages.microsoft.com/repos/edge/pool/main/m/microsoft-edge-stable/microsoft-edge-stable_121.0.2277.128-1_amd64.deb
sudo dpkg -i microsoft-edge-stable_121.0.2277.128-1_amd64.deb

# Install SDKMAN
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"

#open-ssh server
sudo apt install openssh-server -y
sudo ufw allow 22

# Install Java
sdk install java 21.0.1-tem

# Install JetBrains Toolbox for managing JetBrains tools
sudo apt-get install -y fuse libfuse2
wget -cO - "https://download-cdn.jetbrains.com/toolbox/jetbrains-toolbox-2.2.1.19765.tar.gz" | sudo tar -xz -C /opt
sudo chmod +x /opt/jetbrains-toolbox-2.2.1.19765/jetbrains-toolbox
/opt/jetbrains-toolbox-2.2.1.19765/jetbrains-toolbox &


# Install Git
sudo apt-get install -y git

# Install Python3
sudo apt-get install -y python3

#Install Pip3
sudo apt install -y python3-pip

# Install AWS CLI
curl "https://d1vvhvl2y92vvt.cloudfront.net/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Install GCP CLI
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -
sudo apt-get update && sudo apt-get install google-cloud-sdk


#Install Podman
sudo apt install podman -y
echo 'alias docker=podman' >> ~/.bashrc && source ~/.bashrc


#Install podman-compose
pip3 install podman-compose

#Download clamTK
wget https://www.clamav.net/downloads/production/clamav-1.3.0.linux.x86_64.deb
sudo dpkg -i clamav-1.3.0.linux.x86_64.deb

# Install ClamTk Antivirus
sudo apt-get install -y clamtk

# Install KeePass2
sudo apt-get install -y keepass2

# First, update the packages list
sudo apt update

# Next, install the dependencies
sudo apt install software-properties-common apt-transport-https wget

# Import the Microsoft GPG key
wget -q https://packages.microsoft.com/keys/microsoft.asc -O- | sudo apt-key add -

# Enable the Visual Studio Code repository
sudo add-apt-repository "deb [arch=amd64] https://packages.microsoft.com/repos/vscode stable main"

# Finally, install Visual Studio Code
sudo apt update
sudo apt install code