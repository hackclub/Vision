#!/bin/bash

# Hack Club Vision - Quick Start Script

echo "🚀 Starting Hack Club Vision..."

# Check if environment variables are set
if [ -z "$AIRTABLE_PAT" ]; then
    echo "⚠️  Warning: AIRTABLE_PAT environment variable not set"
    echo "   Set it with: export AIRTABLE_PAT='your_token'"
fi

if [ -z "$SHUTTLE_AI_KEY" ]; then
    echo "⚠️  Warning: SHUTTLE_AI_KEY environment variable not set"
    echo "   Set it with: export SHUTTLE_AI_KEY='your_key'"
fi

# Install dependencies if needed
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "📦 Installing dependencies..."
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run the application
echo "✨ Starting Flask application on http://localhost:5000"
python app.py
