# Vision - By Hack Club

**Version 2.0** - Production-ready automated project review system with PostgreSQL, bulk operations, and comprehensive AI analysis.

## 🚀 Key Features

### Core Functionality
- **Account System**: Secure user authentication with session management
- **Multi-Base Support**: Connect unlimited Airtable bases and tables
- **AI Field Detection**: Automatically maps required fields in your tables
- **Field Mapping Editor**: Edit field mappings without re-adding bases

### Advanced Review System
- **4-Step Automated Pipeline**:
  - Step 0: GitHub URL validation (auto-flags non-GitHub links)
  - Step 1: Enhanced duplicate detection with URL normalization
  - Step 2: Comprehensive project testing (quality + originality scores)
  - Step 3: Deep commit analysis (50 commits with detailed stats)
  - Step 4: Strict AI decision with confidence scoring

### Production Features
- **PostgreSQL Support**: Production-grade database with connection pooling
- **Bulk Operations**: Review up to 100 records simultaneously
- **Job Management**: Cancel running jobs, delete completed jobs
- **Production Logging**: Rotating logs with full error tracking
- **Real-time Monitoring**: Track all jobs and their detailed progress

### Review Scoring
- **Quality Score** (1-10): Overall project quality
- **Originality Score** (1-10): Detects templates and tutorials
- **Commit Quality Score** (1-10): Commit message quality
- **Confidence Score** (1-10): AI's confidence in decision

## 📊 Review Criteria

**Auto-Approval Requirements (ALL must pass):**
- Quality ≥ 7/10
- Originality ≥ 6/10
- Working and legitimate project
- Consistent commit pattern
- Code volume matches hours
- No major red flags

**Auto-Rejection Triggers:**
- Duplicate submission
- Non-GitHub URL
- Project not working
- Quality < 4/10
- Originality < 3/10

**Flagged for Manual Review:**
- Marginal quality/originality scores
- Hours mismatch > 5 hours
- Suspicious commit patterns
- Red flags detected

## 🛠️ Setup

### Prerequisites

- Python 3.8+
- PostgreSQL database (or SQLite for local dev)
- Airtable Personal Access Token
- ShuttleAI API Key

### Quick Start (Production)

```bash
# Set environment variables
export DATABASE_URL="postgresql://user:pass@host:5432/dbname"
export AIRTABLE_PAT="your_airtable_personal_access_token"
export SHUTTLE_AI_KEY="your_shuttleai_api_key"

# Run deployment script
./deploy.sh

# Start application
python3 app.py
```

### Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Create database tables
python3 -c "from app import app, db; app.app_context().push(); db.create_all()"

# Start application
python3 app.py
```

### Installation

1. Navigate to the project directory:
```bash
cd hack-club-vision
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Open your browser and navigate to `http://localhost:5000`

## Usage

### 1. Create an Account

- Register a new account on the login page
- Sign in with your credentials

### 2. Add an Airtable Base

- Go to the Dashboard
- Enter your Base ID (e.g., `app3A5kJwYqxMLOgh`)
- Enter the Table Name (e.g., `Projects`)
- Click "Scan & Add Base"

The system will:
- Scan the table structure
- Use AI to detect which fields correspond to:
  - Code URL (GitHub repository)
  - Playable URL (live demo)
  - Hackatime Hours
  - AI Review Notes
  - AI User Feedback
- Create missing fields if needed

### 3. Start a Review

- From the Dashboard, click "Start Review" on a connected base
- Enter the Record ID you want to review
- The system will automatically:
  1. Check if the project was already submitted
  2. Test the project's functionality
  3. Analyze GitHub commits
  4. Generate a review decision (Approved/Rejected/Flagged)
  5. Update the Airtable record with review notes and user feedback

### 4. Monitor Jobs

- Navigate to the Jobs tab
- View running jobs with real-time progress updates
- Review completed jobs with full details

## Unified Database Configuration

The system checks submissions against a unified database:

- **Base ID**: `app3A5kJwYqxMLOgh`
- **Table**: `Approved Projects`
- **Fields**: Email, Playable URL, Code URL

## AI Model

The application uses `openai/gpt-5` via ShuttleAI for:
- Field detection and mapping
- Project functionality testing
- Commit analysis
- Final review decisions

## Architecture

- **Backend**: Flask (Python)
- **Database**: SQLite with SQLAlchemy
- **Frontend**: Tailwind CSS + Font Awesome
- **APIs**: Airtable, ShuttleAI, GitHub
- **Job Processing**: Multi-threaded background jobs

## Review Logic

### Step 1: Duplicate Check
Searches the unified database for matching Code URL or Playable URL

### Step 2: Project Testing
- Fetches the project website
- Analyzes content and features
- Determines if the project is legitimate and functional

### Step 3: Commit Analysis
- Fetches GitHub commit history
- Compares commits to claimed hours
- Identifies commit patterns (consistent vs. bulk)

### Step 4: Finalization
AI determines the final status:
- **Approved**: Project passes all checks
- **Rejected**: Already submitted or project is non-functional
- **Flagged**: Suspicious patterns requiring manual review

## Database Schema

### User
- id (Primary Key)
- username (Unique)
- password
- bases (Relationship)

### AirtableBase
- id (Primary Key)
- user_id (Foreign Key)
- base_id
- table_name
- field_mappings (JSON)

### ReviewJob
- id (Primary Key)
- base_id
- table_name
- record_id
- status
- current_step
- result (JSON)
- created_at

## Security Notes

- Passwords are stored in plaintext (implement hashing for production)
- Use HTTPS in production
- Secure your API keys and environment variables
- Consider rate limiting for API endpoints
