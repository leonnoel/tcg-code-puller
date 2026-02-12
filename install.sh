#!/bin/bash
set -e

echo "=== Pokemon TCG Code Monitor - System Dependencies Installer ==="

# Update package lists
sudo apt-get update -qq

# Install tesseract OCR engine
echo "Installing Tesseract OCR..."
sudo apt-get install -y -qq tesseract-ocr

# Install zbar library for QR code detection
echo "Installing libzbar..."
sudo apt-get install -y -qq libzbar0 libzbar-dev

echo ""
echo "=== System dependencies installed successfully ==="
echo ""
echo "Now install Python dependencies:"
echo "  pip install -r requirements.txt"
