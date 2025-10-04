# Review Criteria - Hack Club Vision v2.0

## Overview

This document outlines the comprehensive review criteria used by Hack Club Vision's AI-powered review system.

---

## Pre-Review Validation

### GitHub URL Check

**Requirement:** Code URL MUST be a GitHub repository link.

**Valid Examples:**
- `https://github.com/username/repository`
- `http://github.com/username/repository`
- `github.com/username/repository`

**Invalid Examples:**
- `https://gitlab.com/username/repository`
- `https://bitbucket.org/username/repository`
- `https://example.com/myproject`
- Empty or missing URL

**Action if Invalid:** Automatically flagged with message to user.

---

## Step 1: Duplicate Detection

### Purpose
Prevent the same project from being submitted multiple times across different tables/bases.

### Checks Performed

1. **URL Normalization:**
   - Remove `http://`, `https://`, `www.`
   - Remove trailing slashes
   - Convert to lowercase

2. **Exact URL Matching:**
   - Compare normalized Code URLs
   - Compare normalized Playable URLs

3. **GitHub Repository Matching:**
   - Extract owner/repo from GitHub URLs
   - Match `github.com/owner/repo` pattern
   - Catches renamed branches or different views of same repo

### Database Checked
`Approved Projects` table in unified Airtable base (app3A5kJwYqxMLOgh)

### Result
- **True:** Project already submitted → Automatic Rejection
- **False:** Unique project → Continue review

---

## Step 2: Project Testing

### Purpose
Verify the project is working, legitimate, and shows original effort.

### Analysis Performed

1. **Content Analysis:**
   - Fetches up to 8000 characters from playable URL
   - Extracts all text content
   - Identifies interactive links

2. **Technical Detection:**
   - Counts forms, buttons, inputs, scripts
   - Detects frameworks (React, Vue, Angular, Bootstrap, Tailwind)
   - Analyzes HTML structure

3. **AI Evaluation:**
   - Is the project functional?
   - Is it legitimate or just a placeholder?
   - Signs of originality vs copied code
   - Quality of implementation

### Scoring System

**Originality Score (1-10):**
- 1-2: Direct copy of tutorial
- 3-5: Template with minimal changes
- 6-7: Template with significant customization
- 8-9: Mostly original with some references
- 10: Completely original implementation

**Quality Score (1-10):**
- 1-2: Broken or non-functional
- 3-4: Basic functionality, poor quality
- 5-6: Working but minimal effort
- 7-8: Good quality, complete features
- 9-10: Excellent quality, polished

### Red Flags Detected

- "Hello World" or tutorial starter code
- Generic placeholder content
- Empty pages or error messages
- No interactive elements
- Copied template without changes
- Lorem ipsum text
- Default framework examples

### Rejection Criteria

**Automatic Rejection if:**
- `is_working = false`
- `is_legitimate = false`
- `quality_score < 4`
- `originality_score < 3`

**Flagged if:**
- `quality_score` between 4-6
- `originality_score` between 3-5
- Any red flags present

**Approval Threshold:**
- `quality_score >= 7`
- `originality_score >= 6`
- `is_working = true`
- `is_legitimate = true`

---

## Step 3: Commit Analysis

### Purpose
Verify claimed hours match actual development effort and quality.

### Data Collected

**Commit Information:**
- Up to 50 most recent commits
- Commit messages
- Author names
- Timestamps
- Lines added/deleted per commit

**Metadata Calculated:**
- Total commits
- Development time span (days)
- Total additions and deletions
- Number of unique authors
- Commit frequency pattern

### Analysis Criteria

**Commit Pattern Types:**

1. **Consistent** (Good):
   - Regular commits over multiple days
   - Gradual progress visible
   - Descriptive commit messages
   - Reasonable code changes per commit

2. **Bulk** (Suspicious):
   - Most commits in single day
   - Large code dumps
   - "Initial commit" with thousands of lines
   - Suggests copied or rushed work

3. **Sparse** (Questionable):
   - Very few commits for claimed hours
   - Long gaps between commits
   - May indicate inflated hours

4. **Suspicious** (Red Flag):
   - All commits at unusual times (3am)
   - Commits at exact intervals (automated?)
   - Generic messages only ("update", "fix")
   - Multiple huge commits

### Scoring System

**Commit Quality Score (1-10):**
- 1-2: Generic messages only ("update", "fix")
- 3-4: Minimal description
- 5-6: Basic but understandable
- 7-8: Descriptive and clear
- 9-10: Excellent detail and context

**Code Volume Analysis:**
- Expected: 20-50 lines per hour for quality code
- Too little: Possibly inflated hours
- Too much in short time: Possibly copied

**Estimated Actual Hours:**
AI estimates realistic hours based on:
- Commit frequency and timing
- Code volume
- Complexity of changes
- Development pattern

### Red Flags Detected

- All commits on single day for 10+ hours claimed
- Only 1-2 commits for 10+ hours claimed
- Huge initial commit (thousands of lines at once)
- All commit messages are generic
- Commits spaced at exact intervals
- Code volume doesn't match time span
- Multiple authors (unless clearly collaborative)

### Rejection/Flag Criteria

**Flagged if:**
- `commits_match_hours = false` AND difference > 5 hours
- `commit_pattern = "suspicious"` or `"bulk"`
- `commit_quality_score < 5`
- `estimated_actual_hours` differs significantly from claimed
- Any red flags detected

**Approval Threshold:**
- `commits_match_hours = true` OR reasonable explanation
- `commit_pattern = "consistent"`
- `commit_quality_score >= 6`
- `code_volume_appropriate = true`

---

## Step 4: Final Decision

### Purpose
Synthesize all data into a final Approved/Rejected/Flagged decision.

### Decision Logic

#### Automatic Rejection

**Any ONE of these causes immediate rejection:**

1. `already_submitted = true` (duplicate)
2. `project_test.is_working = false`
3. `project_test.is_legitimate = false`
4. `project_test.quality_score < 4`
5. `project_test.originality_score < 3`
6. No GitHub repo found
7. No commits found in repository

**User Feedback:** Specific reason for rejection

#### Flag for Manual Review

**Any ONE of these triggers human review:**

1. Hours mismatch > 5 hours
2. Commit pattern is "suspicious" or "bulk"
3. Commit quality score < 5
4. Project quality score between 4-6 (marginal)
5. Project originality score between 3-5 (questionable)
6. Red flags in project test
7. Red flags in commit analysis
8. Estimated actual hours differs significantly

**User Feedback:** Explanation of concerns for reviewer

#### Automatic Approval

**ALL of these must be TRUE:**

1. NOT already submitted
2. `project_test.is_working = true`
3. `project_test.is_legitimate = true`
4. `project_test.quality_score >= 7`
5. `project_test.originality_score >= 6`
6. `commit_review.commits_match_hours = true`
7. `commit_review.commit_pattern = "consistent"`
8. `commit_review.commit_quality_score >= 6`
9. `commit_review.code_volume_appropriate = true`
10. No major red flags

**User Feedback:** Empty (approval is silent)

### Confidence Score

AI also provides a confidence score (1-10) indicating how certain it is of the decision:

- 1-3: Low confidence, should be reviewed
- 4-6: Moderate confidence
- 7-8: High confidence
- 9-10: Very high confidence

Low confidence scores may automatically trigger flagging regardless of decision.

### Review Notes

Detailed internal justification including:
- Specific scores that influenced decision
- Which criteria were met/failed
- Red flags identified
- Reasoning for final decision

These are stored in Airtable's AI Review Notes field.

---

## Approval Statistics (Expected)

Based on strict criteria:

- **~30-40%** Auto-Approved (high quality, clear originality)
- **~40-50%** Flagged for Review (marginal cases, red flags)
- **~10-20%** Auto-Rejected (clear violations, low quality)

This ensures high quality while minimizing false positives.

---

## Examples

### Example 1: Clear Approval

**Submission:**
- Code: `github.com/user/game`
- Hours: 15
- Playable: `user.github.io/game`

**Results:**
- Duplicate: False
- Quality Score: 8/10
- Originality Score: 7/10
- Working: True, Legitimate: True
- Commits: 23 over 5 days
- Commit Pattern: Consistent
- Commit Quality: 7/10
- Estimated Hours: 14

**Decision:** ✅ APPROVED

---

### Example 2: Clear Rejection

**Submission:**
- Code: `github.com/user/template-copy`
- Hours: 10
- Playable: `user.github.io/template`

**Results:**
- Duplicate: False
- Quality Score: 3/10
- Originality Score: 2/10
- Working: True, Legitimate: False
- Red Flags: ["Tutorial copy", "No customization"]

**Decision:** ❌ REJECTED
**Reason:** "Project appears to be an unchanged copy of a tutorial template with minimal effort."

---

### Example 3: Flagged for Review

**Submission:**
- Code: `github.com/user/project`
- Hours: 20
- Playable: `user.github.io/project`

**Results:**
- Duplicate: False
- Quality Score: 6/10 (marginal)
- Originality Score: 5/10 (questionable)
- Working: True, Legitimate: True
- Commits: 3 over 1 day
- Commit Pattern: Bulk
- Estimated Hours: 8

**Decision:** ⚠️ FLAGGED
**Reason:** "Project quality is marginal. All commits made in single day despite 20 hours claimed. Estimated actual effort: 8 hours. Requires human review."

---

### Example 4: Non-GitHub URL

**Submission:**
- Code: `gitlab.com/user/project`
- Hours: 10
- Playable: `example.com`

**Decision:** ⚠️ FLAGGED (immediate)
**Reason:** "Code URL must be a GitHub repository link."

---

## Calibration and Adjustment

Review criteria can be adjusted by modifying the `finalize_review()` function in `app.py`:

### Making Stricter:
- Increase score thresholds
- Add more rejection criteria
- Reduce hour mismatch tolerance

### Making Lenient:
- Decrease score thresholds
- Move rejection criteria to flagging
- Increase hour mismatch tolerance

**Recommended:** Monitor flagged items for 1-2 weeks before adjusting to avoid over-correction.

---

## Maintenance

### Regular Reviews

1. **Weekly:** Review flagged submissions for false positives
2. **Monthly:** Analyze approval/rejection rates
3. **Quarterly:** Update red flag detection based on new patterns

### Quality Metrics

Track over time:
- Approval rate
- Flag rate
- Rejection rate
- False positive rate (approved but should be rejected)
- False negative rate (rejected but should be approved)

---

**Last Updated:** 2025-10-02
**Version:** 2.0
