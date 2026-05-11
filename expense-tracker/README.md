# CJExpenses

Caden Sliney & Jack Vermaak

A personal expense tracker. Users register an account, log in, manually add expenses, or upload receipt photos that get scanned for the merchant, amount, and date.

Built with Flask, PostgreSQL, and AWS (EC2, RDS, S3, Textract).

## Tech Stack

- Flask 3 (Python) for the backend API
- Flask-Login and bcrypt for authentication
- PostgreSQL on AWS RDS for data storage
- AWS S3 for receipt image storage
- AWS Textract for OCR
- Docker for containerization
- Deployed on AWS EC2
- CI/CD via GitHub Actions

## Run Locally

Requires Docker and Docker Compose.

    cp .env.example .env
    docker compose up --build

Visit http://localhost:5000.

## Live URL

http://18.224.182.149

# API Documentation

All endpoints return JSON unless otherwise noted. Most endpoints require authentication via session cookie.

## Setting up Postman

1. Create a new collection called "CJExpenses".
2. Create a Postman environment with a variable `base_url` set to your live URL (e.g. `http://YOUR_EC2_PUBLIC_IP`) or `http://localhost:5000` for local testing.
3. Most endpoints require you to be logged in. Postman automatically stores and sends session cookies, so the workflow is: hit POST /login first, then send your other requests in the same Postman session.

## Authentication

### POST /register

Creates a new user account and logs them in automatically.

Auth required: No
Rate limit: 5 per minute

Request body (form-encoded):

    email=test@example.com
    password=password123
    confirm_password=password123

Response: 302 redirect to dashboard on success, or 400 with flash error on failure.

Postman:
- Method: POST
- URL: {{base_url}}/register
- Body tab, form-data, add three keys: email, password, confirm_password

### POST /login

Logs in an existing user. Sets a session cookie that Postman will use for subsequent requests.

Auth required: No
Rate limit: 5 per minute

Request body (form-encoded):

    email=test@example.com
    password=password123

Response: 302 redirect to dashboard on success, or 401 with flash error.

Postman:
- Method: POST
- URL: {{base_url}}/login
- Body tab, form-data, add two keys: email, password
- After sending, Postman will store the session cookie for your domain

### GET /logout

Logs out the current user.

Auth required: Yes

Response: 302 redirect to login page.

Postman:
- Method: GET
- URL: {{base_url}}/logout

### GET /me

Returns information about the currently logged-in user.

Auth required: Yes

Response 200:

    {
      "id": 1,
      "email": "test@example.com",
      "created_at": "2026-05-10T14:22:10"
    }

Postman:
- Method: GET
- URL: {{base_url}}/me

## Expenses

### GET /api/expenses

Returns all expenses for the currently logged-in user.

Auth required: Yes
Rate limit: 60 per minute

Query parameters (all optional):
- category: filter by category name
- month: filter by month, format YYYY-MM
- start: filter by start date YYYY-MM-DD
- end: filter by end date YYYY-MM-DD

Response 200:

    [
      {
        "id": 1,
        "user_id": 1,
        "merchant": "Starbucks",
        "amount": 6.75,
        "date": "2026-05-10",
        "category": "Food & Dining",
        "description": "Iced latte",
        "receipt_url": "https://your-bucket.s3.amazonaws.com/receipts/...",
        "created_at": "2026-05-10T14:22:10"
      }
    ]

Postman:
- Method: GET
- URL: {{base_url}}/api/expenses
- For filtered results, add query params under the Params tab (e.g. category=Food+%26+Dining&month=2026-05)

### POST /api/expenses

Creates a new expense manually for the logged-in user.

Auth required: Yes
Rate limit: 30 per minute

Request body (JSON):

    {
      "merchant": "Whole Foods",
      "amount": 47.82,
      "date": "2026-05-10",
      "category": "Food & Dining",
      "description": "Weekly groceries"
    }

Required fields: merchant, amount, date
Optional fields: category (defaults to "Uncategorized"), description

Response 201: Created expense object.

Postman:
- Method: POST
- URL: {{base_url}}/api/expenses
- Headers tab, add Content-Type: application/json
- Body tab, raw, JSON, paste the request body above

### GET /api/expenses/:id

Returns a single expense by ID. Only returns expenses owned by the current user.

Auth required: Yes
Rate limit: 60 per minute

Response 200: Single expense object. Returns 404 if not found or not owned by the user.

Postman:
- Method: GET
- URL: {{base_url}}/api/expenses/1

### PUT /api/expenses/:id

Updates an existing expense. Only include the fields you want to change.

Auth required: Yes
Rate limit: 30 per minute

Request body (JSON):

    {
      "amount": 50.00,
      "category": "Shopping"
    }

Any subset of: merchant, amount, date, category, description

Response 200: Updated expense object.

Postman:
- Method: PUT
- URL: {{base_url}}/api/expenses/1
- Headers tab, add Content-Type: application/json
- Body tab, raw, JSON, paste the fields to update

### DELETE /api/expenses/:id

Deletes an expense permanently.

Auth required: Yes
Rate limit: 20 per minute

Response 200:

    { "message": "Deleted", "id": 1 }

Postman:
- Method: DELETE
- URL: {{base_url}}/api/expenses/1

### GET /api/expenses/summary

Returns aggregate statistics for the logged-in user's expenses, used by the dashboard charts.

Auth required: Yes
Rate limit: 30 per minute

Response 200:

    {
      "total": 342.50,
      "count": 18,
      "by_category": [
        { "category": "Food & Dining", "total": 120.30 },
        { "category": "Transportation", "total": 85.00 }
      ],
      "monthly": [
        { "year": 2026, "month": 4, "total": 180.20 },
        { "year": 2026, "month": 5, "total": 162.30 }
      ]
    }

Postman:
- Method: GET
- URL: {{base_url}}/api/expenses/summary

## Uploads

### POST /api/upload

Uploads a receipt image to S3, runs Textract OCR on it, and creates a new expense from the extracted data.

Auth required: Yes
Rate limit: 10 per minute

Request body (multipart/form-data):
- file (required): image file (PNG, JPG, PDF, or TIFF), max 10 MB
- category (optional): override the auto-detected category
- description (optional): optional note

Returns 413 with `{ "error": "File too large. Max size is 10 MB." }` if the upload exceeds the limit.

Response 201:

    {
      "message": "Receipt processed and expense saved.",
      "expense": { ... },
      "ocr_preview": "STARBUCKS\n123 Main St\nIced Latte    $6.75..."
    }

If Textract fails, the expense is still saved with placeholder values and the response includes a warning.

Postman:
- Method: POST
- URL: {{base_url}}/api/upload
- Body tab, form-data, add a key called "file", change its type from Text to File (dropdown next to the key name), select a receipt image

## Health Check

### GET /health

Simple health check endpoint, no auth required.

Response 200:

    { "status": "ok" }

Postman:
- Method: GET
- URL: {{base_url}}/health

# Rate Limits

| Endpoint                  | Limit          |
|---------------------------|----------------|
| Global default            | 200/day, 50/hr |
| POST /register            | 5/min          |
| POST /login               | 5/min          |
| GET /api/expenses         | 60/min         |
| POST /api/expenses        | 30/min         |
| GET /api/expenses/:id     | 60/min         |
| PUT /api/expenses/:id     | 30/min         |
| DELETE /api/expenses/:id  | 20/min         |
| GET /api/expenses/summary | 30/min         |
| POST /api/upload          | 10/min         |

Rate limits are per IP address.
