# Setup Python 3.12 Virtual Environment
# This script recreates the venv with Python 3.12 and installs all dependencies

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host "Python 3.12 Environment Setup for backend/ml" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan
Write-Host ""

$python312 = "C:\Users\Obaidullah Zeeshan\AppData\Local\Programs\Python\Python312\python.exe"
$venvPath = ".\venv"

# Check if Python 3.12 exists
if (-not (Test-Path $python312)) {
    Write-Host "ERROR: Python 3.12 not found at: $python312" -ForegroundColor Red
    Write-Host "Please install Python 3.12 or update the path in this script" -ForegroundColor Yellow
    exit 1
}

# Verify Python version
$version = & $python312 --version
Write-Host "Found: $version" -ForegroundColor Green

# Remove old venv if exists
if (Test-Path $venvPath) {
    Write-Host ""
    Write-Host "Removing old virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $venvPath
    Write-Host "Old venv removed" -ForegroundColor Green
}

# Create new venv with Python 3.12
Write-Host ""
Write-Host "Creating new virtual environment with Python 3.12..." -ForegroundColor Cyan
& $python312 -m venv venv

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
    exit 1
}

Write-Host "Virtual environment created" -ForegroundColor Green

# Activate venv
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip

# Install requirements
Write-Host ""
Write-Host "Installing requirements from requirements.txt..." -ForegroundColor Cyan
Write-Host "This may take several minutes..." -ForegroundColor Yellow
Write-Host ""

pip install -r requirements.txt --default-timeout=300

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Installation completed successfully!" -ForegroundColor Green
    
    # Verify key packages
    Write-Host ""
    Write-Host "Verifying key packages:" -ForegroundColor Cyan
    python -c "import sys; print(f'Python: {sys.version}')"
    python -c "import tensorflow as tf; print(f'TensorFlow: {tf.__version__}')" 2>&1
    python -c "import keras; print(f'Keras: {keras.__version__}')" 2>&1
    python -c "import mediapipe as mp; print(f'MediaPipe: {mp.__version__}')" 2>&1
    python -c "import cv2; print(f'OpenCV: {cv2.__version__}')" 2>&1
    python -c "import numpy as np; print(f'NumPy: {np.__version__}')" 2>&1
    
    Write-Host ""
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host "Setup Complete!" -ForegroundColor Green
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host "To activate the environment, run:" -ForegroundColor Yellow
    Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host ""
    Write-Host "To start the app, run:" -ForegroundColor Yellow
    Write-Host "  python app.py" -ForegroundColor White
    
} else {
    Write-Host ""
    Write-Host "Installation failed!" -ForegroundColor Red
    Write-Host "Check the error messages above for details" -ForegroundColor Yellow
    exit 1
}
