# API Documentation - Hack Club Vision v2.0

## Base URL
```
http://your-domain.com
```

All API endpoints require authentication via Flask session cookies (set after login).

---

## Authentication

### POST /login
Login to the system

**Request:**
```json
{
    "username": "string",
    "password": "string"
}
```

**Response:**
```json
{
    "success": true
}
```

**Errors:**
- 401: Invalid credentials

---

### POST /register
Register a new account

**Request:**
```json
{
    "username": "string",
    "password": "string"
}
```

**Response:**
```json
{
    "success": true
}
```

---

### GET /logout
Logout current user

**Response:** Redirect to login page

---

## Airtable Base Management

### POST /api/add-base
Add and scan a new Airtable base

**Request:**
```json
{
    "base_id": "app3A5kJwYqxMLOgh",
    "table_name": "Projects"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Base added successfully",
    "mappings": {
        "code_url": "GitHub URL",
        "playable_url": "Demo Link",
        "hackatime_hours": "Hours Worked",
        "ai_review_notes": "Internal Notes",
        "ai_user_feedback": "User Feedback"
    }
}
```

**Errors:**
- 400: Error detecting fields
- 400: Base already exists

---

### DELETE /api/delete-base/<int:base_id>
Delete an Airtable base configuration

**Parameters:**
- `base_id` (integer): Database ID of the base

**Response:**
```json
{
    "success": true,
    "message": "Base deleted successfully"
}
```

**Errors:**
- 404: Base not found

---

### POST /api/edit-field-mappings
Edit field mappings for an existing base

**Request:**
```json
{
    "base_id": "app3A5kJwYqxMLOgh",
    "table_name": "Projects",
    "mappings": {
        "code_url": "GitHub Repository",
        "playable_url": "Live Demo",
        "hackatime_hours": "Development Hours",
        "ai_review_notes": "Review Notes",
        "ai_user_feedback": "Feedback"
    }
}
```

**Response:**
```json
{
    "success": true,
    "message": "Field mappings updated successfully"
}
```

**Errors:**
- 404: Base not found
- 400: Missing required field

---

### POST /api/create-field
Update field mapping after creating a field in Airtable

**Request:**
```json
{
    "base_id": "app3A5kJwYqxMLOgh",
    "table_name": "Projects",
    "field_name": "AI Review Notes",
    "field_key": "ai_review_notes",
    "field_type": "multilineText"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Field mapping updated"
}
```

---

## Record Search

### POST /api/search-records
Search for records in an Airtable table

**Request:**
```json
{
    "base_id": "app3A5kJwYqxMLOgh",
    "table_name": "Projects",
    "search_query": "optional search term"
}
```

**Response:**
```json
{
    "records": [
        {
            "id": "rec123abc",
            "fields": {
                "Name": "My Project",
                "GitHub URL": "https://github.com/user/repo",
                "Hours": 15
            }
        }
    ]
}
```

**Limits:**
- Returns first 100 matching records
- Shows only first 20 if search query provided

---

## Review Jobs

### POST /api/start-review
Start a review job for a single record

**Request:**
```json
{
    "base_id": "app3A5kJwYqxMLOgh",
    "table_name": "Projects",
    "record_id": "rec123abc"
}
```

**Response:**
```json
{
    "success": true,
    "message": "Review started"
}
```

**Errors:**
- 400: Base not configured

**Job Processing:**
- Runs in background thread
- Updates database in real-time
- Can be monitored via /api/jobs endpoint

---

### POST /api/bulk-review
Start review jobs for multiple records

**Request:**
```json
{
    "base_id": "app3A5kJwYqxMLOgh",
    "table_name": "Projects",
    "record_ids": [
        "rec123abc",
        "rec456def",
        "rec789ghi"
    ]
}
```

**Response:**
```json
{
    "success": true,
    "message": "Started 3 review jobs",
    "count": 3
}
```

**Limits:**
- Maximum 100 records per bulk operation

**Errors:**
- 400: Too many records (>100)
- 400: Base not configured

---

### GET /api/jobs
Get all running and completed jobs for current user

**Response:**
```json
{
    "running": [
        {
            "id": 123,
            "base_id": "app3A5kJwYqxMLOgh",
            "table_name": "Projects",
            "record_id": "rec123abc",
            "status": "running",
            "current_step": "Step 2: Testing project functionality...",
            "result": null,
            "details": {
                "steps": [
                    {
                        "name": "GitHub URL Validation",
                        "status": "Passed",
                        "result": {
                            "code_url": "https://github.com/user/repo",
                            "is_github": true
                        }
                    },
                    {
                        "name": "Check for Duplicate Submission",
                        "status": "Already submitted: false",
                        "result": {
                            "is_duplicate": false,
                            "code_url": "https://github.com/user/repo",
                            "playable_url": "https://demo.com"
                        }
                    }
                ]
            },
            "created_at": "2025-10-02T17:30:00.000Z",
            "completed_at": null
        }
    ],
    "history": [
        {
            "id": 122,
            "base_id": "app3A5kJwYqxMLOgh",
            "table_name": "Projects",
            "record_id": "rec456def",
            "status": "completed",
            "current_step": "Complete: Approved",
            "result": {
                "status": "Approved",
                "confidence_score": 9,
                "review_notes": "High quality original project. Quality score: 8/10, Originality: 7/10. Consistent commit pattern over 5 days with 23 commits. Code volume appropriate for 15 hours claimed.",
                "user_feedback": ""
            },
            "details": {
                "steps": [
                    {
                        "name": "GitHub URL Validation",
                        "status": "Passed",
                        "result": {"is_github": true}
                    },
                    {
                        "name": "Check for Duplicate Submission",
                        "status": "Already submitted: false",
                        "result": {"is_duplicate": false}
                    },
                    {
                        "name": "Test Project Functionality",
                        "status": "Working: True, Legitimate: True",
                        "result": {
                            "is_working": true,
                            "is_legitimate": true,
                            "originality_score": 7,
                            "quality_score": 8,
                            "features": ["Interactive game", "Score tracking", "Multiple levels"],
                            "red_flags": [],
                            "assessment": "Well-developed game with original mechanics",
                            "technical_details": {
                                "forms": 1,
                                "buttons": 8,
                                "scripts": 12,
                                "frameworks": ["React"]
                            }
                        }
                    },
                    {
                        "name": "Analyze GitHub Commits",
                        "status": "Pattern: consistent, Matches hours: true",
                        "result": {
                            "commits_match_hours": true,
                            "commit_pattern": "consistent",
                            "commit_quality_score": 7,
                            "code_volume_appropriate": true,
                            "estimated_actual_hours": 14,
                            "red_flags": [],
                            "assessment": "Regular development over 5 days",
                            "metadata": {
                                "total_commits": 23,
                                "time_span_days": 5,
                                "total_additions": 847,
                                "total_deletions": 123
                            }
                        }
                    },
                    {
                        "name": "AI Final Decision",
                        "status": "Decision: Approved",
                        "result": {
                            "status": "Approved",
                            "confidence_score": 9,
                            "review_notes": "All criteria met for approval",
                            "user_feedback": ""
                        }
                    }
                ]
            },
            "created_at": "2025-10-02T17:15:00.000Z",
            "completed_at": "2025-10-02T17:16:30.000Z"
        }
    ]
}
```

**Limits:**
- Returns last 100 completed jobs
- All running jobs

---

### POST /api/cancel-job/<int:job_id>
Cancel a running job

**Parameters:**
- `job_id` (integer): Database ID of the job

**Response:**
```json
{
    "success": true,
    "message": "Job cancelled"
}
```

**Errors:**
- 404: Job not found
- 400: Job is not running

**Effect:**
- Job status changed to "cancelled"
- Completion timestamp set
- Job moves to history

---

### DELETE /api/delete-job/<int:job_id>
Delete a completed/failed/cancelled job

**Parameters:**
- `job_id` (integer): Database ID of the job

**Response:**
```json
{
    "success": true,
    "message": "Job deleted"
}
```

**Errors:**
- 404: Job not found
- 400: Cannot delete running job (must cancel first)

**Effect:**
- Permanent deletion from database
- Cannot be recovered

---

## Page Routes

### GET /
Redirect to dashboard (if logged in) or login page

---

### GET /login
Display login page

---

### GET /register
Display registration page

---

### GET /dashboard
Display main dashboard with Airtable bases

**Requires:** Authentication

**Features:**
- Add new bases
- View connected bases
- See field mappings
- Start single reviews
- Delete bases

---

### GET /jobs
Display jobs monitoring page

**Requires:** Authentication

**Features:**
- View running jobs
- View job history (last 100)
- View detailed job information
- Manual refresh button

---

## Error Responses

All endpoints may return these standard error responses:

### 400 Bad Request
```json
{
    "error": "Detailed error message"
}
```

### 401 Unauthorized
```json
{
    "error": "Authentication required"
}
```

### 404 Not Found
```json
{
    "error": "Resource not found"
}
```

### 500 Internal Server Error
```json
{
    "error": "Internal server error",
    "running": [],
    "history": []
}
```

---

## Rate Limiting

**Current Limits:**
- No rate limiting implemented
- Consider adding for production:
  - 100 requests/minute per user
  - 10 bulk reviews/hour per user
  - 1000 API calls/day per user

---

## Webhooks (Future Feature)

Not yet implemented. Potential future endpoints:

- `POST /api/webhooks/airtable` - Receive Airtable webhook events
- `POST /api/webhooks/github` - Receive GitHub webhook events
- `GET /api/webhooks/configure` - Configure webhook settings

---

## Database Schema

### User
```python
{
    "id": Integer (PK),
    "username": String(80, unique),
    "password": String(120)
}
```

### AirtableBase
```python
{
    "id": Integer (PK),
    "user_id": Integer (FK),
    "base_id": String(120),
    "table_name": String(120),
    "field_mappings": Text (JSON string)
}
```

### ReviewJob
```python
{
    "id": Integer (PK),
    "user_id": Integer (FK),
    "base_id": String(120),
    "table_name": String(120),
    "record_id": String(120),
    "status": String(50),  # "running", "completed", "failed", "cancelled"
    "current_step": String(200),
    "result": Text (JSON string),
    "details": Text (JSON string),
    "created_at": DateTime,
    "completed_at": DateTime
}
```

---

## Example Usage

### Complete Review Workflow

```javascript
// 1. Login
await fetch('/login', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        username: 'reviewer',
        password: 'secure_password'
    })
});

// 2. Add Airtable base
const addResponse = await fetch('/api/add-base', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        base_id: 'app3A5kJwYqxMLOgh',
        table_name: 'Submissions'
    })
});

// 3. Search for records
const searchResponse = await fetch('/api/search-records', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        base_id: 'app3A5kJwYqxMLOgh',
        table_name: 'Submissions',
        search_query: 'pending'
    })
});
const {records} = await searchResponse.json();

// 4. Start bulk review
const recordIds = records.map(r => r.id);
await fetch('/api/bulk-review', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
        base_id: 'app3A5kJwYqxMLOgh',
        table_name: 'Submissions',
        record_ids: recordIds
    })
});

// 5. Monitor jobs
const interval = setInterval(async () => {
    const jobsResponse = await fetch('/api/jobs');
    const {running, history} = await jobsResponse.json();

    console.log(`Running: ${running.length}, Completed: ${history.length}`);

    if (running.length === 0) {
        clearInterval(interval);
        console.log('All reviews complete!');
    }
}, 2000);
```

---

**Version:** 2.0
**Last Updated:** 2025-10-02
**Authentication:** Session-based (Flask-Login)
**Content-Type:** application/json
