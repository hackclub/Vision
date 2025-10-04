#!/bin/bash

# Hack Club Vision - Production Deployment Script
# Version 2.0

set -e  # Exit on error

echo "🚀 Hack Club Vision - Production Deployment"
echo "=========================================="
echo ""

# Check environment variables
echo "📋 Checking environment variables..."
if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL not set"
    echo "   Set it with: export DATABASE_URL='postgresql://user:pass@host:5432/dbname'"
    exit 1
fi

if [ -z "$AIRTABLE_PAT" ]; then
    echo "❌ ERROR: AIRTABLE_PAT not set"
    exit 1
fi

if [ -z "$SHUTTLE_AI_KEY" ]; then
    echo "❌ ERROR: SHUTTLE_AI_KEY not set"
    exit 1
fi

echo "✅ All environment variables set"
echo ""

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Create database tables
echo "🗄️  Creating database tables..."
python3 -c "from app import app, db; app.app_context().push(); db.create_all(); print('✅ Database tables created')"
echo ""

# Verify database
echo "🔍 Verifying database..."
python3 << EOF
from app import app, db, User, AirtableBase, ReviewJob
with app.app_context():
    print(f"✅ Users table: {User.query.count()} users")
    print(f"✅ Bases table: {AirtableBase.query.count()} bases")
    print(f"✅ Jobs table: {ReviewJob.query.count()} jobs")
EOF
echo ""

# Create logs directory
echo "📝 Creating logs directory..."
mkdir -p logs
echo "✅ Logs directory created"
echo ""

echo "=========================================="
echo "✅ Deployment complete!"
echo ""
echo "📊 System Status:"
echo "   - Database: Connected ✅"
echo "   - Tables: Created ✅"
echo "   - Logging: Configured ✅"
echo ""
echo "🚀 To start the application:"
echo "   python3 app.py"
echo ""
echo "📚 Documentation:"
echo "   - README.md - Getting started"
echo "   - PRODUCTION_FEATURES.md - Production features"
echo "   - REVIEW_CRITERIA.md - Review criteria"
echo "   - CHANGELOG.md - Version history"
echo ""
echo "🌐 Access the application at:"
echo "   http://localhost:5000"
echo ""
