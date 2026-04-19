# 🚀 Women's Safety System - ML Component

## ⚡ Recent Updates (v2.0)

### ✨ New Features
- 🎯 **Enhanced Gesture Recognition** - 90-95% accuracy (up from 80-85%)
- 📁 **Organized Directory Structure** - Proper data management
- 🧹 **Code Cleanup** - Removed deprecated versions
- 📊 **Quality-Based Training** - Visual feedback for sample quality
- 🔧 **Improved Detection** - 17 comprehensive features
- ⚡ **Better Performance** - 67% reduction in false positives

### 📁 Project Structure
```
backend/ml/
├── data/
│   ├── gestures/      # Trained gesture models
│   ├── images/        # SOS alert captures  
│   ├── cache/         # Location cache
│   └── logs/          # Application logs
├── sos_gesture/       # Gesture detection
├── sos_voice/         # Voice detection
├── get_location/      # Location services
├── app.py            # Main application
├── train_gesture.py  # Training interface
└── quick_test.py     # System verification
```

**📖 Full Documentation:**
- [ENHANCEMENTS.md](ENHANCEMENTS.md) - Detailed improvements
- [GESTURE_DETECTION.md](GESTURE_DETECTION.md) - Technical guide

---

# 🚀 Project Setup Guide (Windows Version)

This guide provides step-by-step instructions to install and run the project on a Windows machine.

---

## ✅ Prerequisites
Ensure the following are installed:

- **Python**: [Download here](https://www.python.org/downloads/)
- **pip** (Python package manager)

To verify the installations, open **Command Prompt** and run:
```bash
python --version //These are the commands to run which are written inside bash
pip --version
```
---

## 📦 Setup Instructions
### 1. Create a Virtual Environment
Create a virtual environment named `venv`:
```bash
python -m venv venv
```
---

### 2. Activate the Virtual Environment
In **Command Prompt**:
```bash
.\venv\Scripts\activate
```
Once activated, your terminal should show `(venv)` at the beginning of the line.
---

### 3. Install Project Dependencies
Install all the required Python packages using `requirements.txt`:
```bash
pip install -r requirements.txt
```
> This process may take 3–5 minutes depending on your internet speed.
---

## ▶️ Run the Application
Start the application with:
```bash
python app.py
```
Your application should now be running!
---