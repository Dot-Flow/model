#!/bin/bash
set -e

echo "Navigating to /home/ubuntu/app..."
cd /home/ubuntu/app

echo "Ownership and permissions of /home/ubuntu/app before creating venv:"
ls -ld /home/ubuntu/app

echo "Creating virtual environment with Python 3.8..."
python3.8 -m venv venv  # python3.8을 명시적으로 사용

echo "Activating virtual environment..."
source venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing dependencies from requirements.txt..."
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

echo "Virtual environment setup complete. Python and pip versions:"
which python
python --version
which pip
pip --version