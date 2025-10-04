
#!/bin/bash

# Hack Club Vision - Dependency Installation Script
echo "🚀 Installing Hack Club Vision dependencies..."

# Check if pip is available
if ! command -v pip &> /dev/null; then
    echo "❌ pip could not be found. Please install Python and pip first."
    exit 1
fi

echo "📦 Installing Flask framework and extensions..."
pip install flask==3.0.0
pip install flask-login==0.6.3
pip install flask-sqlalchemy==3.1.1

echo "📦 Installing database driver..."
pip install psycopg2-binary==2.9.9

echo "📦 Installing Airtable integration..."
pip install pyairtable==2.3.3

echo "📦 Installing AI service..."
pip install shuttleai==3.8.5

echo "📦 Installing HTTP and web scraping libraries..."
pip install requests==2.31.0
pip install beautifulsoup4==4.12.2

echo "📦 Installing environment management..."
pip install python-dotenv==1.0.0

echo "✅ All dependencies installed successfully!"
echo ""
echo "🚀 To start the application, run:"
echo "   python app.py"
echo ""
echo "⚠️  Don't forget to set your environment variables:"
echo "   export AIRTABLE_PAT='your_airtable_token'"
echo "   export SHUTTLE_AI_KEY='your_shuttleai_key'"
