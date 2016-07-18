#!/bin/bash
# ansible prerequisites for ubuntu
[ $(id -u) -ne 0 ] && echo "run as root." && exit 1

PACKAGES=(
    aptitude
    openssh-server
    python
    python-pip
    libffi-dev
    libssl-dev
)

PYTHON_PACKAGES=(
    ansible
    pywinrm
)

apt-get install -y "${PACKAGES[@]}"

SELF=$(who am i|cut -f1 -d" ")
SUDOERS_LINE="$SELF ALL=(ALL) NOPASSWD:ALL"
grep -q "$SUDOERS_LINE" /etc/sudoers || echo "$SUDOERS_LINE" >> /etc/sudoers

pip install --upgrade pip
pip install "${PYTHON_PACKAGES[@]}"
