# Airtable Integration Guide

This guide shows you how to automatically trigger reviews when records are created or updated in Airtable.

## Setup Steps

### 1. Create an API Key

1. Log in to Hack Club Vision
2. Navigate to **API Keys** in the navigation menu
3. Click **Create Key**
4. Give it a descriptive name (e.g., "Airtable Production")
5. **Copy the API key immediately** - you won't see it again!

### 2. Configure Your Base in Hack Club Vision

Before using the API, make sure your Airtable base is configured:

1. Go to **Bases** in Hack Club Vision
2. Click **Add Base**
3. Enter your Base ID and Table Name
4. Let the AI detect field mappings
5. Verify the field mappings are correct

## Airtable Automation Scripts

### Option 1: Automation Script (Recommended)

Create an automation in Airtable that triggers when a record is created or updated.

**Trigger:** When record matches conditions (or when record is created)

**Action:** Run a script

```javascript
// ============================================
// Hack Club Vision - Auto Review Trigger
// ============================================

let config = input.config();
let recordId = config.recordId; // Provided by the trigger

// ==================
// YOUR CONFIGURATION
// ==================
const API_URL = "https://your-app-url.com/api/v1/review";
const API_KEY = "hcv_your_api_key_here"; // Replace with your actual API key
const BASE_ID = "appXXXXXXXXXXXXXX"; // Your Airtable base ID
const TABLE_NAME = "Your Table Name"; // Your table name

// ==================
// SEND REVIEW REQUEST
// ==================
console.log(`🚀 Starting review for record: ${recordId}`);

try {
    let response = await fetch(API_URL, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': API_KEY
        },
        body: JSON.stringify({
            base_id: BASE_ID,
            table_name: TABLE_NAME,
            record_id: recordId
        })
    });

    let result = await response.json();

    if (result.success) {
        console.log('✅ Review started successfully!');
        console.log('Result:', result);
    } else {
        console.error('❌ Error starting review:', result.error);
    }
} catch (error) {
    console.error('❌ Failed to trigger review:', error);
}
```

### Option 2: Conditional Review (Only for Specific Status)

Trigger reviews only when certain conditions are met:

```javascript
// Trigger review only for "Ready for Review" status

let config = input.config();
let recordId = config.recordId;

// Fetch the record to check its status
let table = base.getTable("Your Table Name");
let record = await table.selectRecordAsync(recordId);

// Only proceed if status is "Ready for Review"
if (record.getCellValue("Status") !== "Ready for Review") {
    console.log("⏭️ Skipping review - status is not 'Ready for Review'");
    return;
}

// Configuration
const API_URL = "https://your-app-url.com/api/v1/review";
const API_KEY = "hcv_your_api_key_here";
const BASE_ID = base.id;
const TABLE_NAME = table.name;

// Trigger review
console.log(`🚀 Starting review for record: ${recordId}`);

let response = await fetch(API_URL, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    },
    body: JSON.stringify({
        base_id: BASE_ID,
        table_name: TABLE_NAME,
        record_id: recordId
    })
});

let result = await response.json();
console.log('Review result:', result);
```

### Option 3: Batch Review Multiple Records

Review multiple records at once:

```javascript
// Review all records with a specific status

let table = base.getTable("Your Table Name");
let query = await table.selectRecordsAsync({
    fields: ["Status", "Code URL"]
});

// Configuration
const API_URL = "https://your-app-url.com/api/v1/review";
const API_KEY = "hcv_your_api_key_here";
const BASE_ID = base.id;
const TABLE_NAME = table.name;

let reviewCount = 0;

for (let record of query.records) {
    // Only review records with "Pending" status
    if (record.getCellValue("Status") === "Pending") {
        console.log(`🚀 Starting review for: ${record.id}`);

        try {
            let response = await fetch(API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': API_KEY
                },
                body: JSON.stringify({
                    base_id: BASE_ID,
                    table_name: TABLE_NAME,
                    record_id: record.id
                })
            });

            let result = await response.json();
            if (result.success) {
                reviewCount++;
            }
        } catch (error) {
            console.error(`❌ Failed for ${record.id}:`, error);
        }

        // Add delay to avoid rate limiting (optional)
        await new Promise(resolve => setTimeout(resolve, 1000));
    }
}

console.log(`✅ Started ${reviewCount} reviews`);
```

### Option 4: Button Field Integration

Add a button field that triggers a review when clicked:

1. Add a **Button** field to your table
2. Configure the button to **Run a script**
3. Use this script:

```javascript
// Button click script - Review this record

let table = base.getTable("Your Table Name");
let record = await input.recordAsync('Select a record', table);

if (!record) {
    console.log("No record selected");
    return;
}

// Configuration
const API_URL = "https://your-app-url.com/api/v1/review";
const API_KEY = "hcv_your_api_key_here";
const BASE_ID = base.id;
const TABLE_NAME = table.name;

console.log(`🚀 Starting review for: ${record.name || record.id}`);

let response = await fetch(API_URL, {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-API-Key': API_KEY
    },
    body: JSON.stringify({
        base_id: BASE_ID,
        table_name: TABLE_NAME,
        record_id: record.id
    })
});

let result = await response.json();

if (result.success) {
    console.log('✅ Review started successfully!');
    output.markdown(`# ✅ Review Started\n\nThe AI is now reviewing this project. Check the "AI Review Notes" field in a few minutes.`);
} else {
    console.error('❌ Error:', result.error);
    output.markdown(`# ❌ Error\n\n${result.error}`);
}
```

## Finding Your Base ID

Your Airtable Base ID can be found in the URL when viewing your base:

```
https://airtable.com/appXXXXXXXXXXXXXX/tblYYYYYYYYYYYYYY
                      ^^^^^^^^^^^^^^^^^
                      This is your Base ID
```

## API Endpoint Reference

### POST /api/v1/review

Starts a new review job.

**Headers:**
```
X-API-Key: your_api_key_here
Content-Type: application/json
```

**Body:**
```json
{
    "base_id": "appXXXXXXXXXXXXXX",
    "table_name": "Your Table Name",
    "record_id": "recXXXXXXXXXXXXXX"
}
```

**Response (Success):**
```json
{
    "success": true,
    "message": "Review started",
    "base_id": "appXXXXXXXXXXXXXX",
    "table_name": "Your Table Name",
    "record_id": "recXXXXXXXXXXXXXX"
}
```

**Response (Error):**
```json
{
    "error": "Error message here"
}
```

### GET /api/v1/job/{job_id}

Get the status of a review job.

**Headers:**
```
X-API-Key: your_api_key_here
```

**Response:**
```json
{
    "id": 123,
    "status": "completed",
    "result": {
        "status": "Approved",
        "review_notes": "Great project!",
        "user_feedback": "I loved your responsive design..."
    }
}
```

## Troubleshooting

### "API key required" error
- Make sure you're including the `X-API-Key` header
- Check that your API key is correct

### "Base not configured" error
- Add your base in the Hack Club Vision dashboard first
- Verify the Base ID and Table Name match exactly

### "Invalid or inactive API key" error
- Your API key may have been disabled
- Check the API Keys page and make sure it's active

### Reviews not appearing
- Check that field mappings are correct in your base configuration
- Look at the Jobs page to see if reviews are running

## Security Best Practices

1. **Keep your API key secret** - Don't share it publicly
2. **Use different keys** for different environments (testing vs. production)
3. **Disable unused keys** - Turn off keys you're not using
4. **Rotate keys periodically** - Create new keys and delete old ones
5. **Monitor usage** - Check the "Last Used" timestamp on the API Keys page

## Need Help?

If you run into issues, check the **Jobs** page in Hack Club Vision to see detailed logs and error messages for each review.
