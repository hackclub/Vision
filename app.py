from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from pyairtable import Api
import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import urlparse
import threading
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

# Validate required environment variables
REQUIRED_ENV_VARS = ['AIRTABLE_PAT', 'SHUTTLE_AI_KEY']
missing_vars = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
if missing_vars:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Fix for Heroku postgres:// URLs (change to postgresql://)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///vision.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 10,
    'pool_recycle': 3600,
    'pool_pre_ping': True
}
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Configure logging
if not os.path.exists('logs'):
    os.mkdir('logs')
file_handler = RotatingFileHandler('logs/vision.log', maxBytes=10240000, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Hack Club Vision startup')

# Helper function to normalize GitHub URLs
def normalize_github_url(url):
    """
    Normalize GitHub URLs to the base repository URL.
    Strips everything after github.com/owner/repo

    Examples:
    - https://github.com/user/repo/tree/main -> https://github.com/user/repo
    - https://github.com/user/repo/blob/main/README.md -> https://github.com/user/repo
    - github.com/user/repo/ -> https://github.com/user/repo
    """
    if not url:
        return url

    try:
        # Add https:// if missing
        if not url.startswith('http'):
            url = 'https://' + url

        # Parse the URL
        parsed = urlparse(url)

        # Extract path and get owner/repo
        path_parts = parsed.path.strip('/').split('/')

        if len(path_parts) >= 2:
            owner = path_parts[0]
            repo = path_parts[1]
            # Return normalized URL
            return f"https://github.com/{owner}/{repo}"
        else:
            # Return original if we can't parse it
            return url
    except Exception as e:
        app.logger.warning(f"Failed to normalize GitHub URL '{url}': {e}")
        return url

# Global error handlers
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    app.logger.error(f'Server Error: {error}')
    return jsonify({'error': 'Internal server error'}), 500

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f'Unhandled Exception: {str(e)}', exc_info=True)
    return jsonify({'error': 'An unexpected error occurred'}), 500

# Initialize APIs
airtable_api = Api(os.environ.get('AIRTABLE_PAT'))

# Add custom Jinja2 filter
@app.template_filter('fromjson')
def fromjson_filter(value):
    return json.loads(value)

# AI Helper - wrapper for ShuttleAI calls
def call_ai(prompt, max_tokens=8000, temperature=0.5):
    """Wrapper for ShuttleAI calls using direct HTTP requests with retry logic for rate limits"""
    import time

    api_key = os.environ.get('SHUTTLE_AI_KEY')

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }

    payload = {
        'model': 'anthropic/claude-sonnet-4-20250514',
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': temperature,
        'max_tokens': max_tokens
    }

    max_retries = 30  # Maximum number of retry attempts for rate limits and server errors
    retry_delay = 30  # Wait 30 seconds between retries

    for attempt in range(max_retries):
        try:
            # Timeout is max wait time (90s), not fixed wait - AI will respond as soon as ready
            response = requests.post(
                'https://api.shuttleai.app/v1/chat/completions',
                headers=headers,
                json=payload,
                timeout=90
            )

            # Check for rate limit (429) or server error (500) - retry for both
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    app.logger.warning(f"Rate limited by ShuttleAI (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise Exception("Rate limit exceeded after 30 retries")

            if response.status_code == 500:
                if attempt < max_retries - 1:
                    app.logger.warning(f"ShuttleAI server error 500 (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
                else:
                    raise Exception("Server error 500 persisted after 30 retries")

            response.raise_for_status()
            data = response.json()
            content = data['choices'][0]['message']['content'].strip()

            # Extract JSON from markdown code blocks if present
            if '```json' in content:
                start = content.find('```json') + 7
                end = content.find('```', start)
                content = content[start:end].strip()
            elif '```' in content:
                start = content.find('```') + 3
                end = content.find('```', start)
                content = content[start:end].strip()

            return content

        except requests.exceptions.RequestException as e:
            # Only retry if it's a rate limit error
            if '429' in str(e) or 'rate' in str(e).lower():
                if attempt < max_retries - 1:
                    app.logger.warning(f"Request error (rate limit) (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    continue
            # For other errors, raise immediately
            app.logger.error(f"AI request error: {e}")
            raise

        except Exception as e:
            app.logger.error(f"AI call error: {e}")
            raise

    raise Exception("Rate limit: Maximum 30 retries exceeded")

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    bases = db.relationship('AirtableBase', backref='user', lazy=True)

class AirtableBase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    base_id = db.Column(db.String(120), nullable=False)
    table_name = db.Column(db.String(120), nullable=False)
    field_mappings = db.Column(db.Text)  # JSON string
    custom_instructions = db.Column(db.Text)  # Custom review instructions

class ApiKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    key = db.Column(db.String(128), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)

class ReviewJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    base_id = db.Column(db.String(120), nullable=False)
    table_name = db.Column(db.String(120), nullable=False)
    record_id = db.Column(db.String(120), nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, running, completed, failed, cancelled
    current_step = db.Column(db.String(200))
    result = db.Column(db.Text)  # JSON string with final result
    details = db.Column(db.Text)  # JSON string with all steps
    console_log = db.Column(db.Text)  # JSON array of log messages with timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    cancel_requested = db.Column(db.Boolean, default=False)

    def to_dict(self):
        """Convert job to dictionary for API responses"""
        return {
            'id': self.id,
            'base_id': self.base_id,
            'table_name': self.table_name,
            'record_id': self.record_id,
            'status': self.status,
            'current_step': self.current_step,
            'result': json.loads(self.result) if self.result else None,
            'details': json.loads(self.details) if self.details else None,
            'console_log': json.loads(self.console_log) if self.console_log else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# AI Helper Functions
def ai_detect_fields(table_records, log_fn=None):
    """Use AI to detect which fields correspond to Code URL, Playable URL, etc."""
    if not table_records:
        return None

    # Get sample data to help AI understand the fields
    sample_record = table_records[0]['fields']
    field_names = list(sample_record.keys())

    # Create field examples showing actual data
    field_examples = {}
    for field_name in field_names:
        value = sample_record.get(field_name)
        # Truncate long values
        if isinstance(value, str) and len(value) > 100:
            field_examples[field_name] = value[:100] + "..."
        elif isinstance(value, (list, dict)):
            field_examples[field_name] = str(value)[:100]
        else:
            field_examples[field_name] = value

    prompt = f"""You are analyzing an Airtable table to identify field mappings.

AVAILABLE FIELDS WITH SAMPLE DATA:
{json.dumps(field_examples, indent=2)}

TASK: Match each field to its purpose. Look at the SAMPLE DATA to understand what each field contains.

FIELD PURPOSES TO MATCH:
1. "code_url" - GitHub repository link (look for github.com URLs)
2. "playable_url" - Live demo/project website link (look for deployed site URLs)
3. "hackatime_hours" - Number of hours worked (look for numbers like "10.5" or "15")
4. "auto_review_notes" - Internal review notes field (might be empty or have review text)
5. "auto_user_feedback" - User feedback field (might be empty or have feedback text)
6. "auto_review_tag" - Single select field with values like "Approved" or "Flagged" (review status)

RULES:
- Use the EXACT field name from the list above
- If a field doesn't exist, use null
- Look at the sample data values to determine the correct field
- GitHub links go in code_url, deployed sites go in playable_url

CRITICAL: Respond with ONLY valid JSON, no markdown, no code blocks, no explanations:
{{"code_url": "exact_field_name_or_null", "playable_url": "exact_field_name_or_null", "hackatime_hours": "exact_field_name_or_null", "auto_review_notes": "exact_field_name_or_null", "auto_user_feedback": "exact_field_name_or_null", "auto_review_tag": "exact_field_name_or_null"}}"""

    try:
        if log_fn:
            content = log_fn(prompt, max_tokens=8000, temperature=0.2, step_name="Field Detection")
        else:
            content = call_ai(prompt, max_tokens=8000, temperature=0.2)

        # Extract JSON from markdown if needed (same as other AI calls)
        if '```json' in content:
            start = content.find('```json') + 7
            end = content.find('```', start)
            content = content[start:end].strip()
        elif '```' in content:
            start = content.find('```') + 3
            end = content.find('```', start)
            content = content[start:end].strip()

        result = json.loads(content)

        # Convert null strings to None
        for key in result:
            if result[key] == 'null' or result[key] == 'None':
                result[key] = None

        return result
    except Exception as e:
        print(f"Field detection error: {e}")
        print(f"AI response was: {content if 'content' in locals() else 'No response'}")
        return None

def check_already_submitted(code_url, playable_url):
    """Step 1: Enhanced duplicate check with thorough validation"""
    try:
        unified_base = airtable_api.base('app3A5kJwYqxMLOgh')
        unified_table = unified_base.table('Approved Projects')

        # Normalize URLs for better matching
        def normalize_url(url):
            if not url:
                return None
            url = url.lower().strip()
            # Remove trailing slashes, www, http/https for comparison
            url = url.rstrip('/').replace('https://', '').replace('http://', '').replace('www.', '')
            return url

        norm_code = normalize_url(code_url)
        norm_play = normalize_url(playable_url)

        # Get all records and check manually for better matching
        all_records = unified_table.all()

        for record in all_records:
            fields = record['fields']
            existing_code = normalize_url(fields.get('Code URL', ''))
            existing_play = normalize_url(fields.get('Playable URL', ''))

            # Check for exact matches
            if norm_code and existing_code == norm_code:
                return True
            if norm_play and existing_play == norm_play:
                return True

            # Check if GitHub repo matches (same owner/repo)
            if norm_code and existing_code:
                if 'github.com' in norm_code and 'github.com' in existing_code:
                    code_parts = norm_code.split('github.com/')[-1].split('/')[:2]
                    existing_parts = existing_code.split('github.com/')[-1].split('/')[:2]
                    if len(code_parts) == 2 and len(existing_parts) == 2:
                        if code_parts[0] == existing_parts[0] and code_parts[1] == existing_parts[1]:
                            return True

        return False
    except Exception as e:
        print(f"Error checking unified DB: {e}")
        raise

def test_project(code_url, log_fn=None):
    """Step 2: Deep code analysis - HTML/CSS/JS inspection with smart crawling"""
    import time
    import re
    max_retries = 3
    retry_delay = 5

    for attempt in range(max_retries):
        try:
            # Fetch the main website content
            response = requests.get(code_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            break  # Success, exit retry loop
        except Exception as e:
            if attempt < max_retries - 1:
                app.logger.warning(f"Failed to fetch website (attempt {attempt + 1}/{max_retries}): {e}")
                time.sleep(retry_delay)
                continue
            else:
                # All retries failed - can't access the site
                raise Exception(f"Unable to access website after {max_retries} attempts. The site may be down, private, or blocking automated access: {str(e)}")

    try:
        soup = BeautifulSoup(response.text, 'html.parser')
        page_html = response.text

        # ========== DEEP CODE ANALYSIS ==========

        # Extract ALL CSS (inline, internal, and count external)
        css_code = []
        css_external = 0

        # Inline styles
        for tag in soup.find_all(style=True):
            css_code.append(tag['style'])

        # Internal <style> tags
        for style_tag in soup.find_all('style'):
            css_code.append(style_tag.string or '')

        # External stylesheets
        for link in soup.find_all('link', rel='stylesheet'):
            css_external += 1

        total_css = ''.join(css_code)
        css_lines = len([line for line in total_css.split('\n') if line.strip()])

        # Extract ALL JavaScript (inline, internal, and count external)
        js_code = []
        js_external = 0

        # Inline event handlers
        for tag in soup.find_all(lambda t: any(attr.startswith('on') for attr in t.attrs)):
            for attr in tag.attrs:
                if attr.startswith('on'):
                    js_code.append(tag[attr])

        # Internal <script> tags
        for script_tag in soup.find_all('script'):
            if script_tag.string:
                js_code.append(script_tag.string)
            if not script_tag.get('src'):
                js_code.append(script_tag.string or '')
            else:
                js_external += 1

        total_js = ''.join(js_code)
        js_lines = len([line for line in total_js.split('\n') if line.strip()])

        # Analyze HTML structure
        html_elements = len(soup.find_all())
        custom_classes = set()
        for tag in soup.find_all(class_=True):
            classes = tag.get('class', [])
            custom_classes.update([c for c in classes if not c.startswith(('btn', 'col', 'row', 'container', 'nav', 'card'))])  # Exclude common bootstrap

        custom_ids = len(soup.find_all(id=True))

        # Detect frameworks and libraries more thoroughly
        frameworks = []
        libraries = []

        # Framework detection
        if 'react' in page_html.lower() or '_react' in page_html or 'jsx' in page_html.lower():
            frameworks.append('React')
        if 'vue' in page_html.lower() or 'v-' in page_html:
            frameworks.append('Vue')
        if 'angular' in page_html.lower() or 'ng-' in page_html:
            frameworks.append('Angular')
        if 'svelte' in page_html.lower():
            frameworks.append('Svelte')

        # CSS frameworks
        if 'bootstrap' in page_html.lower():
            libraries.append('Bootstrap')
        if 'tailwind' in page_html.lower():
            libraries.append('Tailwind')
        if 'bulma' in page_html.lower():
            libraries.append('Bulma')
        if 'materialize' in page_html.lower():
            libraries.append('Materialize')

        # JS libraries
        if 'jquery' in page_html.lower():
            libraries.append('jQuery')
        if 'd3' in page_html.lower() or 'chart' in page_html.lower():
            libraries.append('Charting/Data Viz')
        if 'three' in page_html.lower():
            libraries.append('Three.js')
        if 'socket.io' in page_html.lower():
            libraries.append('Socket.io')

        # Detect custom functionality in JS
        js_features = []
        if 'fetch(' in total_js or 'axios' in total_js or 'XMLHttpRequest' in total_js:
            js_features.append('API calls')
        if 'localStorage' in total_js or 'sessionStorage' in total_js:
            js_features.append('Local storage')
        if 'addEventListener' in total_js or 'onclick' in page_html.lower():
            js_features.append('Event handling')
        if 'class ' in total_js and 'constructor' in total_js:
            js_features.append('ES6 classes')
        if 'async ' in total_js or 'await ' in total_js or 'Promise' in total_js:
            js_features.append('Async/Promises')

        # ========== SMART CRAWLING (up to 10 pages) ==========
        from urllib.parse import urljoin, urlparse
        base_domain = urlparse(code_url).netloc

        links = [a.get('href') for a in soup.find_all('a', href=True)]
        internal_links = []

        for link in links:
            if link and not link.startswith('#') and len(internal_links) < 10:
                full_url = urljoin(code_url, link)
                link_domain = urlparse(full_url).netloc

                if link_domain == base_domain and full_url not in [code_url] + internal_links:
                    internal_links.append(full_url)

        crawled_pages = []
        for link_url in internal_links[:10]:  # Crawl up to 10 pages
            try:
                link_response = requests.get(link_url, timeout=3, headers={'User-Agent': 'Mozilla/5.0'})
                link_soup = BeautifulSoup(link_response.text, 'html.parser')

                page_info = {
                    'url': link_url.split('/')[-1] or 'index',  # Just filename for brevity
                    'title': link_soup.title.string if link_soup.title else 'No title',
                    'content_preview': link_soup.get_text()[:500].strip(),
                    'html_elements': len(link_soup.find_all()),
                    'forms': len(link_soup.find_all('form')),
                    'buttons': len(link_soup.find_all('button')),
                    'has_js': bool(link_soup.find_all('script')),
                    'has_custom_css': bool(link_soup.find_all('style')) or bool(link_soup.find_all(style=True))
                }
                crawled_pages.append(page_info)
            except:
                pass

        # Check for interactive elements
        forms = len(soup.find_all('form'))
        buttons = len(soup.find_all('button'))
        inputs = len(soup.find_all('input'))
        scripts = len(soup.find_all('script'))

        # Prepare actual code samples for AI review
        css_sample = total_css[:2000] if total_css else "No custom CSS found"
        js_sample = total_js[:2000] if total_js else "No custom JavaScript found"
        html_sample = str(soup.body)[:2000] if soup.body else str(soup)[:2000]

        # Deep AI code analysis
        prompt = f"""You are reviewing a HIGH SCHOOL student's web project. Analyze the ACTUAL CODE and all pages thoroughly.

========== ACTUAL CODE SAMPLES ==========

HTML STRUCTURE (sample):
{html_sample}

CSS CODE (first 2000 chars):
{css_sample}

JAVASCRIPT CODE (first 2000 chars):
{js_sample}

========== CODE METRICS ==========
HTML: {html_elements} elements, {custom_ids} custom IDs, {len(custom_classes)} custom classes
CSS: {css_lines} internal lines, {css_external} external files
JavaScript: {js_lines} internal lines, {js_external} external files
Features: {', '.join(js_features) if js_features else 'None'}
Frameworks: {', '.join(frameworks + libraries) if frameworks or libraries else 'None'}

========== SITE CRAWL ({len(crawled_pages) + 1} PAGES) ==========
{json.dumps(crawled_pages, indent=2) if crawled_pages else 'Only main page'}

CRITICAL - LOOK AT THE ACTUAL CODE:
1. Check if CSS is custom or just Bootstrap defaults
2. Look at JS code - is it simple or complex logic?
3. Check HTML - template or custom structure?
4. Custom animations, interactions, styling = higher originality
5. Copy-pasted code vs thoughtful implementation
6. Modern techniques (async/await, ES6, APIs) = higher quality

EVALUATION CRITERIA:
- is_working: True if site loads AND has functional elements (check ALL pages)
- is_legitimate: True if shows original work/customization (not 100% template)
- Quality: 3-4 = basic/incomplete, 5-6 = decent effort, 7-8 = good work, 9-10 = excellent
- Originality: 3-4 = mostly template, 5-6 = some customization, 7-8 = original, 9-10 = very creative
- needs_human_review: True if you're uncertain, can't determine quality, see blank pages, or something seems off

⚠️ IMPORTANT - ONLY FLAG FOR REAL UNCERTAINTY:
- ONLY set needs_human_review: true if you literally see BLANK/EMPTY pages or can't load content
- If you see actual content and can evaluate it → make a decision, don't flag
- "Could be AI" is NOT uncertainty - that's what the final review step determines
- Be confident in your assessment - you have enough info to evaluate quality and originality!

RED FLAGS (only if CLEARLY serious):
- Completely unmodified templates (and you're certain)
- Obviously broken core functionality
- Clear tutorial copies with no changes
- Placeholder content everywhere (and you're sure it's not a loading issue)

CRITICAL: Respond with ONLY valid JSON, no markdown, no code blocks, no explanations:
{{"is_working": true/false, "is_legitimate": true/false, "originality_score": 1-10, "features": ["specific feature from page 1", "feature from page 2", "feature from page 3"], "quality_score": 1-10, "red_flags": ["flag if serious"], "assessment": "2-3 sentences covering ALL pages analyzed", "pages_analyzed": {len(crawled_pages) + 1}, "standout_elements": ["impressive element from any page"], "needs_human_review": true/false, "uncertainty_reason": "why flagging for review (if needs_human_review is true)"}}"""

        if log_fn:
            content = log_fn(prompt, max_tokens=8000, temperature=0.3, step_name="Project Test")
        else:
            content = call_ai(prompt, max_tokens=8000, temperature=0.3)
        result = json.loads(content)

        # Add comprehensive technical metadata
        result['technical_details'] = {
            'html_elements': html_elements,
            'custom_classes': len(custom_classes),
            'custom_ids': custom_ids,
            'forms': forms,
            'buttons': buttons,
            'inputs': inputs,
            'scripts': scripts,
            'css_lines': css_lines,
            'css_external': css_external,
            'js_lines': js_lines,
            'js_external': js_external,
            'frameworks': frameworks,
            'libraries': libraries,
            'js_features': js_features,
            'pages_crawled': len(crawled_pages) + 1,
            'response_code': response.status_code
        }

        return result
    except Exception as e:
        print(f"Error testing project: {e}")
        raise

def review_commits(code_url, claimed_hours, log_fn=None):
    """Step 3: Enhanced comprehensive GitHub commit analysis"""
    import time
    max_retries = 3
    retry_delay = 5

    try:
        # Extract GitHub repo from URL
        parsed = urlparse(code_url)
        path_parts = parsed.path.strip('/').split('/')
        if len(path_parts) >= 2:
            owner, repo = path_parts[0], path_parts[1]
            api_url = f"https://api.github.com/repos/{owner}/{repo}/commits"

            # Retry logic for GitHub API access
            for attempt in range(max_retries):
                try:
                    response = requests.get(api_url, timeout=8)
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt < max_retries - 1:
                        app.logger.warning(f"Failed to fetch GitHub commits (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(retry_delay)
                        continue
                    else:
                        # All retries failed
                        raise Exception(f"Unable to access GitHub repository after {max_retries} attempts. The repository may be private, deleted, or GitHub API is down: {str(e)}")

            if response.status_code == 404:
                raise Exception("GitHub repository not found (404). The repository may be private, deleted, or the URL is incorrect.")
            elif response.status_code == 403:
                # Rate limit hit - return neutral data instead of failing
                app.logger.warning("GitHub API rate limit exceeded - skipping commit analysis")
                return {
                    "commits_match_hours": True,  # Neutral - can't verify
                    "commit_pattern": "normal",
                    "commit_quality_score": 7,
                    "estimated_actual_hours": claimed_hours,
                    "code_volume_appropriate": True,
                    "red_flags": [],
                    "assessment": "GitHub API rate limit exceeded - commit analysis skipped. Will rely on project testing for review.",
                    "ai_involvement": "none",  # Neutral assumption
                    "metadata": {
                        "total_commits": 0,
                        "time_span_days": 0,
                        "total_additions": 0,
                        "total_deletions": 0,
                        "total_authors": 1,
                        "note": "Rate limited - data unavailable"
                    }
                }
            elif response.status_code != 200:
                raise Exception(f"GitHub API returned status code {response.status_code}")

            if response.status_code == 200:
                commits = response.json()[:30]  # Get 30 commits for faster analysis

                if len(commits) == 0:
                    raise Exception("No commits found in repository")

                # Extract detailed commit information
                commit_info = []
                total_additions = 0
                total_deletions = 0
                commit_dates = []
                commit_authors = set()

                for commit in commits:
                    commit_data = {
                        'message': commit['commit']['message'],
                        'date': commit['commit']['author']['date'],
                        'author': commit['commit']['author']['name']
                    }

                    commit_dates.append(commit['commit']['author']['date'])
                    commit_authors.add(commit['commit']['author']['name'])

                    # Get detailed stats for commit
                    commit_sha = commit['sha']
                    detail_url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
                    detail_response = requests.get(detail_url, timeout=5)
                    if detail_response.status_code == 200:
                        detail_data = detail_response.json()
                        stats = detail_data.get('stats', {})
                        commit_data['additions'] = stats.get('additions', 0)
                        commit_data['deletions'] = stats.get('deletions', 0)
                        commit_data['total_changes'] = stats.get('total', 0)
                        total_additions += commit_data['additions']
                        total_deletions += commit_data['deletions']

                    commit_info.append(commit_data)

                # Calculate time span
                dates = [datetime.fromisoformat(d.replace('Z', '+00:00')) for d in commit_dates]
                if len(dates) > 1:
                    time_span = (max(dates) - min(dates)).days
                else:
                    time_span = 0

                # Balanced commit analysis for high school students
                prompt = f"""You are reviewing a HIGH SCHOOL student's GitHub commits. Be FAIR but THOROUGH - look for AI assistance patterns.

COMMIT DATA:
Total Commits: {len(commit_info)}
Time Span: {time_span} days
Total Code Changes: +{total_additions} -{total_deletions}
Authors: {', '.join(commit_authors)}
Claimed Hours: {claimed_hours}

DETAILED COMMITS (first 30):
{json.dumps(commit_info[:30], indent=2)}

CRITICAL: LOOK FOR AI-GENERATED CODE INDICATORS
Examine commit messages for these AI patterns:
1. Messages with "Assistant", "AI", "Claude", "ChatGPT", "Copilot"
2. Messages like "Add feature" with massive code changes (1000+ lines)
3. Perfect code all at once with no iterations
4. Author names like "GitHub Copilot", "assistant", "bot"
5. Commits that say "Update from AI" or similar

AI USAGE SCORING:
- "none": No AI detected, student wrote code themselves
- "light": Used AI for help/debugging, but student clearly coded
- "heavy": Most code generated by AI, student mainly prompted
- "complete": Entirely AI-generated with zero student coding

EVALUATION:
1. **AI Involvement Check (MOST IMPORTANT)**:
   - Look at commit messages for AI keywords
   - Check if code volume matches claimed hours
   - Massive changes in minutes = AI generated

2. Time analysis:
   - Does {claimed_hours} hours match commit pattern?
   - AI-heavy projects: estimated_actual_hours = 20-40% of claimed
   - Student-coded: estimated_actual_hours can match or exceed claimed

3. Commit pattern:
   - "consistent": Regular work across multiple sessions
   - "learning": Trial-and-error, iterations (good sign!)
   - "suspicious": All at once, or AI-generated

RED FLAGS (mark if found):
- Commit messages mention AI/Assistant
- Claimed 20 hours but all code in 1-2 massive commits
- 1000+ line changes in single commit with "Add feature" message
- Author field shows AI tool names

⚠️ MAKING THE CALL ON AI INVOLVEMENT:
- You have commit messages, timestamps, code volume, and patterns - USE THEM
- Large commits CAN be legitimate (copy-paste from local dev, migrations, library files)
- Look at the CONTENT of messages, not just size
- If commits show iteration, debugging, fixes → probably student coded
- If ALL code in 1-2 commits with generic messages → likely AI or copied
- Make a determination - don't flag for uncertainty unless commits are literally missing or empty!

CRITICAL: Respond with ONLY valid JSON, no markdown, no code blocks, no explanations:
{{"commits_match_hours": true/false, "commit_pattern": "consistent/learning/suspicious", "commit_quality_score": 1-10, "code_volume_appropriate": true/false, "ai_involvement": "none/light/heavy/complete", "estimated_actual_hours": number, "red_flags": ["specific AI indicators found"], "assessment": "1-2 sentences on AI usage and time accuracy", "needs_human_review": true/false, "uncertainty_reason": "why flagging for review (if needs_human_review is true)"}}"""

                if log_fn:
                    content = log_fn(prompt, max_tokens=8000, temperature=0.3, step_name="Commit Review")
                else:
                    content = call_ai(prompt, max_tokens=8000, temperature=0.3)
                result = json.loads(content)

                # Add metadata
                result['metadata'] = {
                    'total_commits': len(commit_info),
                    'time_span_days': time_span,
                    'total_additions': total_additions,
                    'total_deletions': total_deletions,
                    'total_authors': len(commit_authors)
                }

                return result

        raise Exception("Invalid GitHub URL or repository not found")
    except Exception as e:
        print(f"Error reviewing commits: {e}")
        raise

def finalize_review(already_submitted, project_test, commit_review, claimed_hours, custom_instructions=None, log_fn=None):
    """Step 4: Final decision with balanced criteria and ALWAYS meaningful feedback"""

    # Extract AI involvement from commit review
    ai_involvement = commit_review.get('ai_involvement', 'none')
    estimated_hours = commit_review.get('estimated_actual_hours', claimed_hours)

    custom_instructions_text = f"\n\nCUSTOM REVIEW INSTRUCTIONS:\n{custom_instructions}\n" if custom_instructions else ""

    prompt = f"""You are reviewing a HIGH SCHOOL student's project. Make a FAIR decision and provide GENUINE, ENTHUSIASTIC feedback.

SUBMISSION DATA:
Already Submitted: {already_submitted}
Claimed Hours: {claimed_hours}

PROJECT TEST RESULTS:
{json.dumps(project_test, indent=2)}

COMMIT ANALYSIS:
{json.dumps(commit_review, indent=2)}{custom_instructions_text}

⚠️ CRITICAL AI INVOLVEMENT CHECK:
AI Involvement Level: {ai_involvement}
- "none" = Student wrote all code themselves ✅
- "light" = Used AI for help, but student clearly coded ✅
- "heavy" = Most code AI-generated, student mainly prompted ⚠️
- "complete" = Entirely AI-generated with zero student coding ❌

Estimated Actual Hours: {estimated_hours} (vs claimed {claimed_hours})

DECISION CRITERIA (ONLY TWO OPTIONS: Approved or Flagged):

⚠️ IMPORTANT: If the project is a desktop/mobile app (features includes "Desktop/mobile application"), it will have neutral scores (7/10) because we can't test it online. This is NORMAL and OKAY - don't flag it for that!

FLAG if (needs human review - ONLY SERIOUS ISSUES):
1. already_submitted = True (duplicate - must verify)
2. ai_involvement = "complete" (100% AI with zero student work)
3. quality_score < 3 (completely broken or unusable)
4. MULTIPLE serious red flags combined (not just one)
5. Clear evidence of cheating/plagiarism
6. Project is completely non-functional

APPROVE if (MOST of these - be generous):
1. ai_involvement = "none" or "light" (student did real work)
2. quality_score >= 4 OR originality_score >= 4 (show some effort!)
3. Project works and shows learning
4. No CLEAR evidence of 100% AI generation
5. Even if time is off or commits are messy - students make mistakes!

⚠️ ABOUT SUSPICIOUS COMMITS:
- "suspicious" commits alone is NOT enough to flag
- Large commits happen (local dev, bulk uploads, migrations)
- Time discrepancies happen (forgot to commit, worked offline)
- ONLY flag if ai_involvement = "complete" AND multiple other red flags
- Give students the benefit of the doubt!

REQUIRED OUTPUT (ALWAYS include both):

1. review_notes (2-3 sentences):
   - Technical quality and features
   - AI involvement assessment
   - Time accuracy
   - Any concerns

2. user_feedback (ALWAYS provide - be HUMAN and CONVERSATIONAL):
   FOR APPROVALS - Be genuinely excited like talking to a friend:
   - "Wow, I really liked..." or "This is awesome -..." or "Nice work on..."
   - Mention SPECIFIC cool features you saw
   - Sound like a real person, not a robot
   - 2-3 sentences max, keep it natural

   FOR FLAGS (needs human review):
   - Be friendly and understanding, not robotic
   - Explain why without sounding like a lawyer
   - BAD: "The commit pattern suggests additional verification is required"
   - GOOD: "I noticed the commit history looks a bit off - could you help me understand the timeline better?"
   - For duplicates: "Hey, this looks really similar to another submission I saw. Is this the same project or something different?"
   - For quality: "This has potential but I think it needs a bit more work before it's ready to go"
   - For AI concerns: "The commits make me wonder if some AI tools helped with the heavy lifting here - totally fine if so, just want to verify!"
   - Always sound like you're helping, not judging

CRITICAL: Respond with ONLY valid JSON, no markdown, no code blocks, no explanations:
{{"status": "Approved/Flagged", "confidence_score": 1-10, "review_notes": "2-3 concise sentences for internal review", "user_feedback": "2-3 sentences - sound like a REAL PERSON talking, not a robot"}}"""

    if log_fn:
        content = log_fn(prompt, max_tokens=8000, temperature=0.2, step_name="Final Review")
    else:
        content = call_ai(prompt, max_tokens=8000, temperature=0.2)
    return json.loads(content)

def run_review_job(user_id, base_id, table_name, record_id, field_mappings, custom_instructions=None):
    """Run the complete review process with database persistence"""
    with app.app_context():
        app.logger.info(f'Starting review job for user {user_id}, base {base_id}, record {record_id}')

        if custom_instructions:
            app.logger.info(f'Using custom instructions for review: {custom_instructions[:100]}...')

        # Create job in database
        job = ReviewJob(
            user_id=user_id,
            base_id=base_id,
            table_name=table_name,
            record_id=record_id,
            status='running',
            current_step='Initializing...',
            details=json.dumps({'steps': []}),
            console_log=json.dumps([]),
            cancel_requested=False
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

        app.logger.info(f'Created job #{job_id} in database')

        job_details = {'steps': []}
        console_logs = []

        def log_console(message, level='info'):
            """Add a message to the console log"""
            timestamp = datetime.utcnow().isoformat()
            console_logs.append({
                'timestamp': timestamp,
                'level': level,
                'message': message
            })
            job = ReviewJob.query.get(job_id)
            job.console_log = json.dumps(console_logs)
            db.session.commit()

        def call_ai_with_logging(prompt, max_tokens=500, temperature=0.5, step_name=""):
            """Wrapper for AI calls with detailed logging"""
            log_console(f'🤖 Calling ShuttleAI API...')
            log_console(f'   Model: anthropic/claude-sonnet-4-20250514')
            log_console(f'   Temperature: {temperature}')
            log_console(f'   Max Tokens: {max_tokens}')
            log_console(f'   Timeout: 90s')
            log_console(f'📝 Prompt sent ({len(prompt)} chars):')
            # Log prompt in chunks to make it readable
            prompt_lines = prompt.split('\n')[:15]  # First 15 lines
            for line in prompt_lines:
                if line.strip():
                    log_console(f'   {line[:100]}')
            total_lines = len(prompt.split('\n'))
            if total_lines > 15:
                remaining = total_lines - 15
                log_console(f'   ... ({remaining} more lines)')

            try:
                result = call_ai(prompt, max_tokens, temperature)
                log_console(f'✅ AI Response received ({len(result)} chars)')
                log_console(f'📄 Full AI Response:')
                # Log response in chunks
                response_lines = result.split('\n')
                for line in response_lines:
                    if line.strip():
                        log_console(f'   {line}')
                return result
            except Exception as e:
                log_console(f'❌ AI call failed: {str(e)}', 'error')
                raise

        def check_cancellation():
            """Check if job cancellation was requested"""
            job = ReviewJob.query.get(job_id)
            return job and job.cancel_requested

        log_console('🚀 Job initialized - starting review process')

        try:
            # Get record from Airtable
            log_console(f'📡 Fetching record from Airtable (Base: {base_id}, Table: {table_name}, Record: {record_id})')
            base = airtable_api.base(base_id)
            table = base.table(table_name)
            record = table.get(record_id)
            fields = record['fields']
            log_console(f'✅ Record fetched successfully - {len(fields)} fields found')

            # Extract data using field mappings
            mappings = json.loads(field_mappings)
            code_url = fields.get(mappings.get('code_url', ''))
            playable_url = fields.get(mappings.get('playable_url', ''))
            hackatime_hours = fields.get(mappings.get('hackatime_hours', ''), 0)

            # Normalize GitHub URL (strip everything after owner/repo)
            if code_url and 'github.com' in code_url.lower():
                original_url = code_url
                code_url = normalize_github_url(code_url)
                if original_url != code_url:
                    log_console(f'🔧 Normalized GitHub URL:')
                    log_console(f'   From: {original_url}')
                    log_console(f'   To: {code_url}')

            log_console(f'📋 Extracted data:')
            log_console(f'   • Code URL: {code_url}')
            log_console(f'   • Playable URL: {playable_url}')
            log_console(f'   • Claimed Hours: {hackatime_hours}')

            # Step 0: Validate GitHub URL
            if check_cancellation():
                raise Exception("Job cancelled by user")

            log_console('🔍 STEP 0: Validating GitHub URL...')
            job = ReviewJob.query.get(job_id)
            job.current_step = 'Validating GitHub URL...'
            db.session.commit()

            if not code_url or 'github.com' not in code_url.lower():
                log_console(f'❌ GitHub URL validation FAILED - Not a valid GitHub URL', 'error')
                final_decision = {
                    "status": "Flagged",
                    "review_notes": "Code URL is not a GitHub link. Must be a valid GitHub repository URL.",
                    "user_feedback": "I couldn't find a GitHub repo in your Code URL field. I need a GitHub link (like https://github.com/username/repo) so I can look at your commits and code. If your code is somewhere else, could you upload it to GitHub? That way I can properly review your work!"
                }
                job_details['steps'].append({
                    'name': 'GitHub URL Validation',
                    'status': 'Failed - Not a GitHub URL',
                    'error': 'Code URL must be a GitHub link',
                    'result': {'code_url': code_url, 'is_github': False}
                })
                log_console(f'⚠️ Flagging submission due to invalid GitHub URL')

                # Update job and exit
                job.status = 'completed'
                job.current_step = 'Flagged: Invalid GitHub URL'
                job.result = json.dumps(final_decision)
                job.details = json.dumps(job_details)
                job.completed_at = datetime.utcnow()
                db.session.commit()

                # Update Airtable
                update_fields = {}
                if mappings.get('auto_review_notes'):
                    update_fields[mappings['auto_review_notes']] = final_decision['review_notes']
                if mappings.get('auto_user_feedback'):
                    update_fields[mappings['auto_user_feedback']] = final_decision['user_feedback']
                if mappings.get('auto_review_tag'):
                    update_fields[mappings['auto_review_tag']] = final_decision['status']
                if update_fields:
                    table.update(record_id, update_fields)

                return

            log_console(f'✅ GitHub URL validation PASSED')
            job_details['steps'].append({
                'name': 'GitHub URL Validation',
                'status': 'Passed',
                'result': {'code_url': code_url, 'is_github': True}
            })

            # Step 1: Check if already submitted
            if check_cancellation():
                raise Exception("Job cancelled by user")

            log_console('🔍 STEP 1: Checking for duplicate submissions...')
            log_console(f'   Querying unified database (app3A5kJwYqxMLOgh/Approved Projects)')
            job = ReviewJob.query.get(job_id)
            job.current_step = 'Step 1: Checking for duplicates...'
            db.session.commit()

            try:
                already_submitted = check_already_submitted(code_url, playable_url)
                if already_submitted:
                    log_console(f'❌ DUPLICATE FOUND - This project was already submitted!', 'warning')
                else:
                    log_console(f'✅ No duplicate found - Original submission')
                job_details['steps'].append({
                    'name': 'Check for Duplicate Submission',
                    'status': f'Already submitted: {already_submitted}',
                    'result': {'is_duplicate': already_submitted, 'code_url': code_url, 'playable_url': playable_url}
                })
            except Exception as e:
                job_details['steps'].append({
                    'name': 'Check for Duplicate Submission',
                    'status': 'Failed',
                    'error': str(e)
                })
                already_submitted = False

            # Step 2: Test project
            if check_cancellation():
                raise Exception("Job cancelled by user")

            log_console('🔍 STEP 2: Testing project functionality...')

            # Check if playable_url is a video link, file, or missing (indicates desktop/mobile app)
            video_platforms = ['youtube.com', 'youtu.be', 'loom.com', 'vimeo.com', 'streamable.com', 'drive.google.com', 'dropbox.com']
            github_file_patterns = ['github.com', '/blob/', '/raw/', '.mp4', '.mov', '.avi', '.mkv', '.mp3', '.wav', '.zip', '.tar', '.gz']
            is_video_or_app = False

            if playable_url:
                playable_lower = playable_url.lower()
                # Check if it's a video platform OR a GitHub file link
                is_video_or_app = (
                    any(platform in playable_lower for platform in video_platforms) or
                    any(pattern in playable_lower for pattern in github_file_patterns)
                )
            else:
                is_video_or_app = True  # No playable URL = likely desktop/mobile app

            if is_video_or_app:
                log_console(f'📱 Detected desktop/mobile app or video demo - skipping web testing')
                log_console(f'   Project type: {"Video demo link" if playable_url else "Desktop/mobile app (no web URL)"}')
                project_test = {
                    "is_working": True,  # Assume working since we can't test
                    "is_legitimate": True,
                    "features": ["Desktop/mobile application"],
                    "quality_score": 7,  # Neutral score
                    "originality_score": 7,
                    "assessment": "Desktop/mobile app or video demo - cannot test web functionality. Will rely on commit analysis and code review."
                }
                job_details['steps'].append({
                    'name': 'Test Project Functionality',
                    'status': 'Skipped - Desktop/Mobile App',
                    'result': project_test
                })
            else:
                log_console(f'   Fetching website: {playable_url}')
                job = ReviewJob.query.get(job_id)
                job.current_step = 'Step 2: Testing project functionality...'
                db.session.commit()

                try:
                    log_console(f'   Parsing HTML and extracting features...')
                    project_test = test_project(playable_url, log_fn=call_ai_with_logging)
                    log_console(f'✅ Project Test Complete!')
                    log_console(f'   • Is Working: {project_test.get("is_working")}')
                    log_console(f'   • Is Legitimate: {project_test.get("is_legitimate")}')
                    log_console(f'   • Quality Score: {project_test.get("quality_score", "N/A")}/10')
                    log_console(f'   • Originality Score: {project_test.get("originality_score", "N/A")}/10')
                    job_details['steps'].append({
                        'name': 'Test Project Functionality',
                        'status': f'Working: {project_test.get("is_working")}, Legitimate: {project_test.get("is_legitimate")}',
                        'result': project_test
                    })
                except Exception as e:
                    error_str = str(e).lower()

                    # Check if this is an API error (500, rate limit, etc) - these should fail the job
                    if '500 server error' in error_str or 'api.shuttleai' in error_str or 'rate limit' in error_str:
                        log_console(f'❌ Critical API Error in Project Test: {str(e)}', 'error')
                        raise Exception(f'API Error during project testing: {str(e)}')

                    # Check if we can't access the website - flag it for human review
                    if 'unable to access website' in error_str:
                        log_console(f'⚠️ Cannot access website - flagging for manual review', 'warning')
                        final_decision = {
                            "status": "Flagged",
                            "review_notes": f"Unable to access the playable URL after multiple attempts: {str(e)}",
                            "user_feedback": "I tried visiting your project's website but couldn't get through - it might be down, need a login, or just not like robots very much! I'm sending this to a human reviewer so they can check it out properly. Don't worry, we'll make sure your project gets reviewed!"
                        }

                        # Update Airtable and complete the job
                        update_fields = {}
                        if mappings.get('auto_review_notes'):
                            update_fields[mappings['auto_review_notes']] = final_decision['review_notes']
                        if mappings.get('auto_user_feedback'):
                            update_fields[mappings['auto_user_feedback']] = final_decision['user_feedback']
                        if mappings.get('auto_review_tag'):
                            update_fields[mappings['auto_review_tag']] = final_decision['status']
                        if update_fields:
                            table.update(record_id, update_fields)

                        job = ReviewJob.query.get(job_id)
                        job.status = 'completed'
                        job.current_step = 'Flagged: Site inaccessible'
                        job.result = json.dumps(final_decision)
                        job.details = json.dumps(job_details)
                        job.console_log = json.dumps(console_logs)
                        job.completed_at = datetime.utcnow()
                        db.session.commit()
                        return

                    # Non-API errors (like website timeout) can continue with degraded data
                    log_console(f'⚠️ Project test encountered non-critical error: {str(e)}', 'warning')
                    project_test = {"is_working": False, "is_legitimate": False, "features": [], "assessment": f"Error: {str(e)}"}
                    job_details['steps'].append({
                        'name': 'Test Project Functionality',
                        'status': 'Failed',
                        'error': str(e),
                        'result': project_test
                    })

            # Step 3: Review commits
            if check_cancellation():
                raise Exception("Job cancelled by user")

            log_console('🔍 STEP 3: Analyzing GitHub commits...')
            log_console(f'   Fetching commits from GitHub API')
            job = ReviewJob.query.get(job_id)
            job.current_step = 'Step 3: Analyzing GitHub commits...'
            db.session.commit()

            try:
                log_console(f'   Requesting commit history (up to 30 commits)...')
                commit_review = review_commits(code_url, hackatime_hours, log_fn=call_ai_with_logging)
                log_console(f'✅ Commit Analysis Complete!')
                log_console(f'   • Fetched {commit_review.get("metadata", {}).get("total_commits", 0)} commits')
                log_console(f'   • Pattern: {commit_review.get("commit_pattern", "N/A")}')
                log_console(f'   • Matches Hours: {commit_review.get("commits_match_hours")}')
                log_console(f'   • Commit Quality: {commit_review.get("commit_quality_score", "N/A")}/10')
                log_console(f'   • Estimated Hours: {commit_review.get("estimated_actual_hours", "N/A")}')
                job_details['steps'].append({
                    'name': 'Analyze GitHub Commits',
                    'status': f'Pattern: {commit_review.get("commit_pattern")}, Matches hours: {commit_review.get("commits_match_hours")}',
                    'result': commit_review
                })
            except Exception as e:
                error_str = str(e).lower()

                # Check if this is an API error (500, rate limit, etc) - these should fail the job
                if '500 server error' in error_str or 'api.shuttleai' in error_str or 'rate limit' in error_str:
                    log_console(f'❌ Critical API Error in Commit Analysis: {str(e)}', 'error')
                    raise Exception(f'API Error during commit analysis: {str(e)}')

                # Check if we can't access the GitHub repo - flag it for human review
                if 'unable to access github' in error_str or 'repository not found' in error_str or 'repository may be private' in error_str:
                    log_console(f'⚠️ Cannot access GitHub repository - flagging for manual review', 'warning')
                    final_decision = {
                        "status": "Flagged",
                        "review_notes": f"Unable to access GitHub repository: {str(e)}",
                        "user_feedback": "I couldn't access your GitHub repo to check out your commits. It might be set to private, the link might be off, or maybe it got deleted? Double-check that your repo is public and the link is right. Either way, I'm flagging this for a human to review!"
                    }

                    # Update Airtable and complete the job
                    update_fields = {}
                    if mappings.get('auto_review_notes'):
                        update_fields[mappings['auto_review_notes']] = final_decision['review_notes']
                    if mappings.get('auto_user_feedback'):
                        update_fields[mappings['auto_user_feedback']] = final_decision['user_feedback']
                    if mappings.get('auto_review_tag'):
                        update_fields[mappings['auto_review_tag']] = final_decision['status']
                    if update_fields:
                        table.update(record_id, update_fields)

                    job = ReviewJob.query.get(job_id)
                    job.status = 'completed'
                    job.current_step = 'Flagged: GitHub repo inaccessible'
                    job.result = json.dumps(final_decision)
                    job.details = json.dumps(job_details)
                    job.console_log = json.dumps(console_logs)
                    job.completed_at = datetime.utcnow()
                    db.session.commit()
                    return

                # Non-API errors (like GitHub API issues) can continue with degraded data
                log_console(f'⚠️ Commit analysis encountered non-critical error: {str(e)}', 'warning')
                commit_review = {"commits_match_hours": False, "commit_pattern": "error", "assessment": f"Error: {str(e)}"}
                job_details['steps'].append({
                    'name': 'Analyze GitHub Commits',
                    'status': 'Failed',
                    'error': str(e),
                    'result': commit_review
                })

            # Step 4: Finalize
            if check_cancellation():
                raise Exception("Job cancelled by user")

            log_console('🔍 STEP 4: Making final decision...')
            log_console(f'   Combining all previous analysis results')
            job = ReviewJob.query.get(job_id)
            job.current_step = 'Step 4: Finalizing review...'
            db.session.commit()

            try:
                # Check if any step flagged for REAL technical issues (not just "could be AI")
                needs_review_reasons = []

                # Only flag if there's a TECHNICAL problem (blank pages, can't load, etc)
                if project_test.get('needs_human_review'):
                    reason = project_test.get('uncertainty_reason', '')
                    # Only flag for technical issues, not analysis uncertainty
                    if 'blank' in reason.lower() or 'empty' in reason.lower() or 'cannot load' in reason.lower() or 'error' in reason.lower():
                        needs_review_reasons.append(f"Project testing: {reason}")

                # Commits flagged for uncertainty is NOT a reason to skip final review
                # The final AI decision can handle "suspicious" commits

                # If REAL technical uncertainty detected, flag immediately
                if needs_review_reasons:
                    log_console(f'⚠️ Technical issue detected - flagging for human review', 'warning')
                    for reason in needs_review_reasons:
                        log_console(f'   • {reason}')

                    final_decision = {
                        "status": "Flagged",
                        "confidence_score": 3,
                        "review_notes": f"Technical issues prevented automated review: {'; '.join(needs_review_reasons)}",
                        "user_feedback": "Hey! I ran into some technical issues trying to load your project - might be a loading problem, auth requirement, or something on my end. I'm sending this to a human reviewer to check it out properly. It might take a bit longer, but we'll make sure your work gets reviewed!"
                    }
                else:
                    # Proceed with normal AI final decision (even if commits are "suspicious")
                    final_decision = finalize_review(already_submitted, project_test, commit_review, hackatime_hours, custom_instructions=custom_instructions, log_fn=call_ai_with_logging)

                log_console(f'✅ Final Decision Made!')
                log_console(f'   🎯 Decision: {final_decision.get("status")}')
                log_console(f'   📊 Confidence: {final_decision.get("confidence_score", "N/A")}/10')
                if final_decision.get("status") == "Approved":
                    log_console(f'   ✅ Project APPROVED for submission!', 'success')
                elif final_decision.get("status") == "Rejected":
                    log_console(f'   ❌ Project REJECTED', 'error')
                else:
                    log_console(f'   ⚠️ Project FLAGGED for manual review', 'warning')
                job_details['steps'].append({
                    'name': 'Auto Final Decision',
                    'status': f'Decision: {final_decision.get("status")}',
                    'result': final_decision
                })
            except Exception as e:
                # Check if this is an API error (500, rate limit, etc) - these MUST fail the job
                error_str = str(e).lower()
                if '500 server error' in error_str or 'api.shuttleai' in error_str or 'rate limit' in error_str:
                    log_console(f'❌ Critical API Error in Final Decision: {str(e)}', 'error')
                    raise Exception(f'API Error during final decision: {str(e)}')

                # Other errors in final decision should also fail the job (can't make a decision)
                log_console(f'❌ Failed to make final decision: {str(e)}', 'error')
                raise Exception(f'Failed to finalize review: {str(e)}')

            # Update Airtable with results
            log_console('💾 Updating Airtable with review results...')
            update_fields = {}
            if mappings.get('auto_review_notes'):
                update_fields[mappings['auto_review_notes']] = final_decision['review_notes']
            if mappings.get('auto_user_feedback') and final_decision.get('user_feedback'):
                update_fields[mappings['auto_user_feedback']] = final_decision['user_feedback']
            if mappings.get('auto_review_tag'):
                update_fields[mappings['auto_review_tag']] = final_decision['status']

            if update_fields:
                try:
                    # Use threading timeout for background thread compatibility
                    import concurrent.futures

                    def update_airtable():
                        return table.update(record_id, update_fields)

                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(update_airtable)
                        try:
                            future.result(timeout=15)  # 15 second timeout
                            log_console(f'✅ Airtable updated with {len(update_fields)} fields')
                        except concurrent.futures.TimeoutError:
                            log_console('⚠️ Airtable update timed out (15s), continuing anyway...', 'warning')
                except Exception as airtable_error:
                    log_console(f'⚠️ Airtable update failed: {str(airtable_error)}', 'warning')
                    log_console('Review completed but could not update Airtable record', 'warning')

            log_console('🎉 Review process completed successfully!')
            log_console(f'📋 Summary: {final_decision["status"]} - Job #{job_id} complete')

            job = ReviewJob.query.get(job_id)
            job.status = 'completed'
            job.current_step = f'Complete: {final_decision["status"]}'
            job.result = json.dumps(final_decision)
            job.details = json.dumps(job_details)
            job.console_log = json.dumps(console_logs)  # Ensure console logs are saved
            job.completed_at = datetime.utcnow()
            db.session.commit()

        except Exception as e:
            job = ReviewJob.query.get(job_id)

            # Check if this was a cancellation
            if "cancelled by user" in str(e).lower():
                job.status = 'cancelled'
                job.current_step = 'Cancelled by user'
                job.result = json.dumps({'status': 'Cancelled', 'message': 'Job cancelled by user'})
            else:
                job.status = 'failed'
                job.current_step = f'Error: {str(e)}'
                job.result = json.dumps({'status': 'Error', 'error': str(e)})
                job_details['steps'].append({
                    'name': 'Fatal Error',
                    'status': 'Failed',
                    'error': str(e)
                })

                # Update Airtable with Error status
                log_console(f'❌ Job failed with error: {str(e)}', 'error')
                log_console('💾 Updating Airtable with Error status...')
                try:
                    mappings = json.loads(field_mappings)
                    update_fields = {}

                    if mappings.get('auto_review_notes'):
                        update_fields[mappings['auto_review_notes']] = f'Error during review: {str(e)}'
                    if mappings.get('auto_user_feedback'):
                        update_fields[mappings['auto_user_feedback']] = 'Oops! Something went wrong on my end while reviewing your project. This is totally a me problem, not yours. Could you reach out to support or try submitting again? Sorry about the hassle!'
                    if mappings.get('auto_review_tag'):
                        update_fields[mappings['auto_review_tag']] = 'Error'

                    if update_fields:
                        base = airtable_api.base(base_id)
                        table = base.table(table_name)
                        table.update(record_id, update_fields)
                        log_console(f'✅ Airtable updated with Error status')
                except Exception as airtable_error:
                    log_console(f'⚠️ Failed to update Airtable with error status: {str(airtable_error)}', 'warning')

            job.details = json.dumps(job_details)
            job.console_log = json.dumps(console_logs)  # Ensure console logs are saved
            job.completed_at = datetime.utcnow()
            db.session.commit()

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        user = User.query.filter_by(username=data['username']).first()
        if user and user.password == data['password']:
            login_user(user)
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'success': False, 'error': 'Username exists'}), 400
        user = User(username=data['username'], password=data['password'])
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return jsonify({'success': True})
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Explicitly query bases to ensure all fields are loaded
    bases = AirtableBase.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', bases=bases)

@app.route('/api/add-base', methods=['POST'])
@login_required
def add_base():
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']

    try:
        # Scan table and detect fields
        base = airtable_api.base(base_id)
        table = base.table(table_name)
        records = table.all(max_records=5)

        field_mappings = ai_detect_fields(records)

        if not field_mappings:
            return jsonify({'error': 'Could not detect fields'}), 400

        # Check if fields exist, create if missing
        missing_fields = []
        if records:
            for key in ['code_url', 'playable_url', 'hackatime_hours', 'auto_review_notes', 'auto_user_feedback', 'auto_review_tag']:
                if not field_mappings.get(key) or field_mappings[key] == 'null' or field_mappings[key] is None:
                    missing_fields.append(key)

        # Save to database
        new_base = AirtableBase(
            user_id=current_user.id,
            base_id=base_id,
            table_name=table_name,
            field_mappings=json.dumps(field_mappings)
        )
        db.session.add(new_base)
        db.session.commit()

        return jsonify({
            'success': True,
            'base_id': new_base.id,
            'field_mappings': field_mappings,
            'missing_fields': missing_fields if missing_fields else []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/search-records', methods=['POST'])
@login_required
def search_records():
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']
    search_query = data.get('search_query', '')

    try:
        base = airtable_api.base(base_id)
        table = base.table(table_name)

        # Get all records (limited to 100)
        records = table.all(max_records=100)

        # Filter records based on search query
        filtered_records = []
        for record in records:
            record_data = {
                'id': record['id'],
                'fields': record['fields']
            }

            # If search query exists, filter by field values
            if search_query:
                field_values = ' '.join(str(v) for v in record['fields'].values()).lower()
                if search_query.lower() in field_values:
                    filtered_records.append(record_data)
            else:
                filtered_records.append(record_data)

        return jsonify({'records': filtered_records[:20]})  # Return max 20 results
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/start-review', methods=['POST'])
@login_required
def start_review():
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']
    record_id = data['record_id']

    # Find the base configuration
    base_config = AirtableBase.query.filter_by(
        user_id=current_user.id,
        base_id=base_id,
        table_name=table_name
    ).first()

    if not base_config:
        return jsonify({'error': 'Base not configured'}), 400

    # Start review in background thread
    thread = threading.Thread(
        target=run_review_job,
        args=(current_user.id, base_id, table_name, record_id, base_config.field_mappings, base_config.custom_instructions)
    )
    thread.start()

    return jsonify({'success': True, 'message': 'Review started'})

@app.route('/api/delete-base/<int:base_id>', methods=['DELETE'])
@login_required
def delete_base(base_id):
    try:
        base = AirtableBase.query.filter_by(id=base_id, user_id=current_user.id).first()
        if not base:
            return jsonify({'error': 'Base not found'}), 404

        db.session.delete(base)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/create-field', methods=['POST'])
@login_required
def create_field():
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']
    field_name = data['field_name']
    field_type = data.get('field_type', 'singleLineText')

    try:
        # Note: Airtable API doesn't support field creation via API
        # We'll update the field mapping to use the newly created field
        base_config = AirtableBase.query.filter_by(
            user_id=current_user.id,
            base_id=base_id,
            table_name=table_name
        ).first()

        if not base_config:
            return jsonify({'error': 'Base not found'}), 404

        # Update field mappings
        mappings = json.loads(base_config.field_mappings)
        field_key = data['field_key']  # e.g., 'auto_review_notes'
        mappings[field_key] = field_name

        base_config.field_mappings = json.dumps(mappings)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Field mapping updated'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/api/edit-field-mappings', methods=['POST'])
@login_required
def edit_field_mappings():
    """Edit field mappings for a base"""
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']
    new_mappings = data['mappings']

    app.logger.info(f'Edit field mappings request: base_id={base_id}, table_name={table_name}, user_id={current_user.id}')

    try:
        base_config = AirtableBase.query.filter_by(
            user_id=current_user.id,
            base_id=base_id,
            table_name=table_name
        ).first()

        if not base_config:
            # Log all bases for this user to debug
            all_bases = AirtableBase.query.filter_by(user_id=current_user.id).all()
            app.logger.error(f'Base not found. Available bases: {[(b.id, b.base_id, b.table_name) for b in all_bases]}')
            return jsonify({'error': f'Base not found. Searched for base_id={base_id}, table_name={table_name}'}), 404

        # Validate mappings
        required_fields = ['code_url', 'playable_url', 'hackatime_hours', 'auto_review_notes', 'auto_user_feedback', 'auto_review_tag']
        for field in required_fields:
            if field not in new_mappings:
                return jsonify({'error': f'Missing required field: {field}'}), 400

        base_config.field_mappings = json.dumps(new_mappings)
        db.session.commit()

        app.logger.info(f'User {current_user.id} updated field mappings for base {base_id}')
        return jsonify({'success': True, 'message': 'Field mappings updated successfully'})
    except Exception as e:
        app.logger.error(f'Error updating field mappings: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/update-custom-instructions', methods=['POST'])
@login_required
def update_custom_instructions():
    """Update custom review instructions for a base"""
    data = request.json
    db_id = data['db_id']
    custom_instructions = data.get('custom_instructions', '')

    try:
        base_config = AirtableBase.query.filter_by(
            id=db_id,
            user_id=current_user.id
        ).first()

        if not base_config:
            return jsonify({'error': 'Base not found'}), 404

        base_config.custom_instructions = custom_instructions
        db.session.commit()

        app.logger.info(f'User {current_user.id} updated custom instructions for base {db_id}')
        return jsonify({'success': True, 'message': 'Custom instructions updated successfully'})
    except Exception as e:
        app.logger.error(f'Error updating custom instructions: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/rescan-fields', methods=['POST'])
@login_required
def rescan_fields():
    """Re-scan and detect field mappings for a base"""
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']
    db_id = data['db_id']

    try:
        base_config = AirtableBase.query.filter_by(
            id=db_id,
            user_id=current_user.id
        ).first()

        if not base_config:
            return jsonify({'error': 'Base not found'}), 404

        # Scan table and detect fields
        base = airtable_api.base(base_id)
        table = base.table(table_name)
        records = table.all(max_records=5)

        field_mappings = ai_detect_fields(records)

        if not field_mappings:
            return jsonify({'error': 'Could not detect fields'}), 400

        # Update field mappings
        base_config.field_mappings = json.dumps(field_mappings)
        db.session.commit()

        app.logger.info(f'User {current_user.id} re-scanned field mappings for base {base_id}')
        return jsonify({'success': True, 'message': 'Field mappings re-scanned successfully', 'field_mappings': field_mappings})
    except Exception as e:
        app.logger.error(f'Error re-scanning fields: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/bulk-review', methods=['POST'])
@login_required
def bulk_review():
    """Start reviews for multiple records at once"""
    data = request.json
    base_id = data['base_id']
    table_name = data['table_name']
    record_ids = data['record_ids']  # List of record IDs

    if len(record_ids) > 100:
        return jsonify({'error': 'Maximum 100 records per bulk operation'}), 400

    try:
        base_config = AirtableBase.query.filter_by(
            user_id=current_user.id,
            base_id=base_id,
            table_name=table_name
        ).first()

        if not base_config:
            return jsonify({'error': 'Base not configured'}), 400

        # Start review for each record in separate threads
        threads = []
        for record_id in record_ids:
            thread = threading.Thread(
                target=run_review_job,
                args=(current_user.id, base_id, table_name, record_id, base_config.field_mappings, base_config.custom_instructions)
            )
            thread.start()
            threads.append(thread)

        app.logger.info(f'User {current_user.id} started bulk review of {len(record_ids)} records')
        return jsonify({
            'success': True,
            'message': f'Started {len(record_ids)} review jobs',
            'count': len(record_ids)
        })
    except Exception as e:
        app.logger.error(f'Error starting bulk review: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/cancel-job/<int:job_id>', methods=['POST'])
@login_required
def cancel_job(job_id):
    """Cancel a running job - force stop immediately"""
    try:
        job = ReviewJob.query.filter_by(id=job_id, user_id=current_user.id).first()

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        if job.status != 'running':
            return jsonify({'error': 'Job is not running'}), 400

        # Force cancel immediately - don't wait for thread to check
        job.status = 'cancelled'
        job.cancel_requested = True
        job.current_step = 'Cancelled by user'
        job.completed_at = datetime.utcnow()
        job.result = json.dumps({'status': 'Cancelled', 'message': 'Job forcefully cancelled by user'})
        db.session.commit()

        app.logger.info(f'User {current_user.id} forcefully cancelled job {job_id}')
        return jsonify({'success': True, 'message': 'Job cancelled'})
    except Exception as e:
        app.logger.error(f'Error cancelling job: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/delete-job/<int:job_id>', methods=['DELETE'])
@login_required
def delete_job(job_id):
    """Delete a completed/failed job from history"""
    try:
        job = ReviewJob.query.filter_by(id=job_id, user_id=current_user.id).first()

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        if job.status == 'running':
            return jsonify({'error': 'Cannot delete running job'}), 400

        db.session.delete(job)
        db.session.commit()

        app.logger.info(f'User {current_user.id} deleted job {job_id}')
        return jsonify({'success': True, 'message': 'Job deleted'})
    except Exception as e:
        app.logger.error(f'Error deleting job: {str(e)}')
        return jsonify({'error': str(e)}), 400

@app.route('/api/jobs')
@login_required
def get_jobs():
    try:
        # Get running jobs from database
        running_jobs = ReviewJob.query.filter_by(
            user_id=current_user.id,
            status='running'
        ).order_by(ReviewJob.created_at.desc()).all()

        # Get completed/failed/cancelled jobs from database (last 100)
        history_jobs = ReviewJob.query.filter(
            ReviewJob.user_id == current_user.id,
            ReviewJob.status.in_(['completed', 'failed', 'cancelled'])
        ).order_by(ReviewJob.created_at.desc()).limit(100).all()

        app.logger.info(f'User {current_user.id} fetched {len(running_jobs)} running and {len(history_jobs)} history jobs')

        return jsonify({
            'running': [job.to_dict() for job in running_jobs],
            'history': [job.to_dict() for job in history_jobs]
        })
    except Exception as e:
        app.logger.error(f'Error fetching jobs for user {current_user.id}: {str(e)}')
        return jsonify({'error': str(e), 'running': [], 'history': []}), 500

@app.route('/jobs')
@login_required
def jobs():
    return render_template('jobs.html')

@app.route('/api/job/<int:job_id>')
@login_required
def get_job(job_id):
    """Get a single job by ID for the current user"""
    try:
        job = ReviewJob.query.filter_by(id=job_id, user_id=current_user.id).first()

        if not job:
            return jsonify({'error': 'Job not found'}), 404

        return jsonify(job.to_dict())
    except Exception as e:
        app.logger.error(f'Error fetching job {job_id}: {str(e)}')
        return jsonify({'error': str(e)}), 500

# API Key Management Routes
@app.route('/api-keys')
@login_required
def api_keys_page():
    api_keys = ApiKey.query.filter_by(user_id=current_user.id).all()
    return render_template('api_keys.html', api_keys=api_keys)

@app.route('/api/create-api-key', methods=['POST'])
@login_required
def create_api_key():
    data = request.json
    name = data.get('name', 'API Key')

    # Generate random API key
    import secrets
    api_key = 'hcv_' + secrets.token_urlsafe(48)

    new_key = ApiKey(
        user_id=current_user.id,
        key=api_key,
        name=name
    )
    db.session.add(new_key)
    db.session.commit()

    app.logger.info(f'User {current_user.id} created API key: {name}')
    return jsonify({
        'success': True,
        'api_key': api_key,
        'name': name,
        'id': new_key.id,
        'created_at': new_key.created_at.isoformat()
    })

@app.route('/api/delete-api-key/<int:key_id>', methods=['DELETE'])
@login_required
def delete_api_key(key_id):
    api_key = ApiKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if not api_key:
        return jsonify({'error': 'API key not found'}), 404

    db.session.delete(api_key)
    db.session.commit()

    app.logger.info(f'User {current_user.id} deleted API key: {api_key.name}')
    return jsonify({'success': True})

@app.route('/api/toggle-api-key/<int:key_id>', methods=['POST'])
@login_required
def toggle_api_key(key_id):
    api_key = ApiKey.query.filter_by(id=key_id, user_id=current_user.id).first()
    if not api_key:
        return jsonify({'error': 'API key not found'}), 404

    api_key.is_active = not api_key.is_active
    db.session.commit()

    return jsonify({'success': True, 'is_active': api_key.is_active})

# Public API Endpoints (require API key authentication)
def require_api_key(f):
    """Decorator to require valid API key"""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key') or request.args.get('api_key')

        if not api_key:
            return jsonify({'error': 'API key required'}), 401

        key_obj = ApiKey.query.filter_by(key=api_key, is_active=True).first()
        if not key_obj:
            return jsonify({'error': 'Invalid or inactive API key'}), 401

        # Update last used timestamp
        key_obj.last_used = datetime.utcnow()
        db.session.commit()

        # Pass user_id to the route
        return f(user_id=key_obj.user_id, *args, **kwargs)

    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route('/api/v1/review', methods=['POST'])
@require_api_key
def api_start_review(user_id):
    """Start a review job via API"""
    data = request.json

    base_id = data.get('base_id')
    table_name = data.get('table_name')
    record_id = data.get('record_id')

    if not all([base_id, table_name, record_id]):
        return jsonify({'error': 'Missing required fields: base_id, table_name, record_id'}), 400

    # Find the base configuration
    base_config = AirtableBase.query.filter_by(
        user_id=user_id,
        base_id=base_id,
        table_name=table_name
    ).first()

    if not base_config:
        return jsonify({'error': 'Base not configured. Please add the base in the dashboard first.'}), 400

    # Start review in background thread
    thread = threading.Thread(
        target=run_review_job,
        args=(user_id, base_id, table_name, record_id, base_config.field_mappings, base_config.custom_instructions)
    )
    thread.start()

    app.logger.info(f'API: Started review for user {user_id}, base {base_id}, record {record_id}')
    return jsonify({
        'success': True,
        'message': 'Review started',
        'base_id': base_id,
        'table_name': table_name,
        'record_id': record_id
    })

@app.route('/api/v1/job/<int:job_id>', methods=['GET'])
@require_api_key
def api_get_job(user_id, job_id):
    """Get job status via API"""
    job = ReviewJob.query.filter_by(id=job_id, user_id=user_id).first()

    if not job:
        return jsonify({'error': 'Job not found'}), 404

    return jsonify(job.to_dict())

if __name__ == '__main__':
    with app.app_context():
        # Migration: Increase api_key.key column size
        try:
            from sqlalchemy import text
            db.session.execute(text('''
                ALTER TABLE api_key
                ALTER COLUMN key TYPE VARCHAR(128)
            '''))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.info(f'Migration already applied or table does not exist: {e}')

        # Migration: Add custom_instructions column to airtable_base
        try:
            from sqlalchemy import text
            db.session.execute(text('''
                ALTER TABLE airtable_base
                ADD COLUMN IF NOT EXISTS custom_instructions TEXT
            '''))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            app.logger.info(f'Migration already applied or table does not exist: {e}')

        # Migration: Rename ai_* fields to auto_* in existing field_mappings
        try:
            bases = AirtableBase.query.all()
            for base in bases:
                if base.field_mappings:
                    mappings = json.loads(base.field_mappings)
                    updated = False

                    # Migrate old field names to new ones
                    if 'ai_review_notes' in mappings:
                        mappings['auto_review_notes'] = mappings.pop('ai_review_notes')
                        updated = True
                    if 'ai_user_feedback' in mappings:
                        mappings['auto_user_feedback'] = mappings.pop('ai_user_feedback')
                        updated = True

                    # Add auto_review_tag if missing (set to null initially)
                    if 'auto_review_tag' not in mappings:
                        mappings['auto_review_tag'] = None
                        updated = True

                    if updated:
                        base.field_mappings = json.dumps(mappings)
                        app.logger.info(f'Migrated field mappings for base {base.id}')

            if bases:
                db.session.commit()
                app.logger.info(f'Field mapping migration completed for {len(bases)} bases')
        except Exception as e:
            db.session.rollback()
            app.logger.info(f'Field mapping migration failed or not needed: {e}')

        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
