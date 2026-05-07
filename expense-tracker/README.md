# CJExpenses — Automated Expense Tracker
**Caden Sliney & Jack Vermaak**

A full-stack expense tracking web application deployed on AWS using **Path A (Traditional)** architecture:
EC2 + Docker + RDS (PostgreSQL) + S3 + Amazon Textract.

---

## Architecture Overview

```
User Browser
     │
     ▼
[ EC2 Instance ]
[ Docker Container: Flask + Gunicorn ]
     │              │              │
     ▼              ▼              ▼
[ RDS PostgreSQL ] [ S3 Bucket ] [ Amazon Textract ]
 (expense data)    (receipts)    (OCR on receipts)
     
GitHub → GitHub Actions → ECR → EC2 (CI/CD)
```

---

## Tech Stack

| Layer        | Technology                     |
|--------------|--------------------------------|
| Backend      | Flask 3 (Python)               |
| Database     | PostgreSQL 16 on AWS RDS       |
| Storage      | AWS S3                         |
| OCR          | Amazon Textract                |
| Hosting      | AWS EC2 (t3.micro) + Docker    |
| CI/CD        | GitHub Actions + Amazon ECR    |
| Rate Limiting| Flask-Limiter                  |

---

## Local Development

### Prerequisites
- Docker & Docker Compose
- AWS credentials (for S3 + Textract)

### 1. Clone and configure
```bash
git clone https://github.com/YOUR_USERNAME/expense-tracker.git
cd expense-tracker
cp .env.example .env
# Edit .env with your AWS credentials and S3 bucket name
```

### 2. Run locally
```bash
docker-compose up --build
```
App will be available at http://localhost:5000

### 3. Run without Docker (bare Python)
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL="postgresql://postgres:password@localhost:5432/expensedb"
python run.py
```

---

## AWS Deployment

### Required AWS Resources

1. **EC2** — Amazon Linux 2023, t3.micro, with security group allowing HTTP (80) and SSH (22)
2. **RDS** — PostgreSQL 16, db.t3.micro, in same VPC as EC2
3. **S3** — Create a bucket (e.g. `my-expense-tracker-receipts`)
4. **ECR** — Create repository named `expense-tracker`
5. **IAM Role** — Attach to EC2 with:
   - `AmazonS3FullAccess`
   - `AmazonTextractFullAccess`
   - `AmazonEC2ContainerRegistryReadOnly`

### EC2 First-Time Setup
```bash
# SSH into your instance
ssh -i your-key.pem ec2-user@YOUR_EC2_PUBLIC_IP

# Install Docker
sudo yum update -y
sudo yum install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

# Install AWS CLI
sudo yum install -y awscli
```

### GitHub Secrets to Configure
Set these in your GitHub repo → Settings → Secrets:

| Secret                  | Value                                         |
|-------------------------|-----------------------------------------------|
| `AWS_ACCOUNT_ID`        | Your 12-digit AWS account ID                  |
| `AWS_ACCESS_KEY_ID`     | IAM user key (for GitHub Actions CI only)     |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret                               |
| `AWS_REGION`            | e.g. `us-east-1`                              |
| `EC2_HOST`              | Your EC2 public IP or DNS                     |
| `EC2_SSH_KEY`           | Contents of your `.pem` private key           |
| `DATABASE_URL`          | Full RDS connection string                    |
| `SECRET_KEY`            | Random string for Flask sessions              |
| `S3_BUCKET`             | Your S3 bucket name                           |

Push to `main` and GitHub Actions will build, push to ECR, and deploy automatically.

---

## API Documentation

Base URL: `http://YOUR_EC2_IP` (or `http://localhost:5000` locally)

All endpoints return JSON. Rate limits are enforced per IP address.

---

### `GET /health`
Health check.

**Response:**
```json
{ "status": "ok" }
```

---

### `GET /api/expenses`
Returns all expenses. Supports optional query filters.

**Rate limit:** 60/minute

**Query Parameters:**

| Param      | Type   | Description                          |
|------------|--------|--------------------------------------|
| `category` | string | Filter by category name              |
| `month`    | string | Filter by month, format `YYYY-MM`    |
| `start`    | string | Filter by start date `YYYY-MM-DD`    |
| `end`      | string | Filter by end date `YYYY-MM-DD`      |

**Example request:**
```
GET /api/expenses?category=Food+%26+Dining&month=2024-06
```

**Example response:**
```json
[
  {
    "id": 1,
    "merchant": "Starbucks",
    "amount": 6.75,
    "date": "2024-06-15",
    "category": "Food & Dining",
    "description": "Iced latte",
    "receipt_url": "https://your-bucket.s3.amazonaws.com/receipts/...",
    "created_at": "2024-06-15T14:22:10"
  }
]
```

---

### `POST /api/expenses`
Creates a new expense manually.

**Rate limit:** 30/minute

**Request body (JSON):**
```json
{
  "merchant": "Whole Foods",
  "amount": 47.82,
  "date": "2024-06-20",
  "category": "Food & Dining",
  "description": "Weekly groceries"
}
```

| Field         | Type    | Required | Description                  |
|---------------|---------|----------|------------------------------|
| `merchant`    | string  | ✅       | Store or vendor name          |
| `amount`      | number  | ✅       | Positive decimal amount       |
| `date`        | string  | ✅       | ISO date `YYYY-MM-DD`         |
| `category`    | string  | No       | Defaults to `Uncategorized`   |
| `description` | string  | No       | Optional notes                |

**Response:** `201 Created` with the created expense object.

---

### `GET /api/expenses/:id`
Get a single expense by ID.

**Rate limit:** 60/minute

**Response:** Single expense object or `404`.

---

### `PUT /api/expenses/:id`
Update an existing expense. Only include fields you want to change.

**Rate limit:** 30/minute

**Request body (JSON):** Any subset of: `merchant`, `amount`, `date`, `category`, `description`

**Response:** Updated expense object.

---

### `DELETE /api/expenses/:id`
Delete an expense permanently.

**Rate limit:** 20/minute

**Response:**
```json
{ "message": "Deleted", "id": 1 }
```

---

### `GET /api/expenses/summary`
Returns aggregate statistics for charts and dashboard.

**Rate limit:** 30/minute

**Response:**
```json
{
  "total": 342.50,
  "count": 18,
  "by_category": [
    { "category": "Food & Dining", "total": 120.30 },
    { "category": "Transportation", "total": 85.00 }
  ],
  "monthly": [
    { "year": 2024, "month": 5, "total": 180.20 },
    { "year": 2024, "month": 6, "total": 162.30 }
  ]
}
```

---

### `POST /api/upload`
Upload a receipt image to S3, run Textract OCR, and save the parsed expense.

**Rate limit:** 10/minute

**Request:** `multipart/form-data`

| Field         | Type   | Required | Description                         |
|---------------|--------|----------|-------------------------------------|
| `file`        | file   | ✅       | Image file (PNG, JPG, PDF, TIFF)    |
| `category`    | string | No       | Override auto-detected category     |
| `description` | string | No       | Optional note                       |

**Response:** `201 Created`
```json
{
  "message": "Receipt processed and expense saved.",
  "expense": { ...expense object... },
  "ocr_preview": "STARBUCKS\n123 Main St\nIced Latte    $6.75\nTotal         $6.75..."
}
```

---

## Rate Limiting Summary

| Endpoint                       | Limit        |
|--------------------------------|--------------|
| Global default                 | 200/day, 50/hr |
| `GET /api/expenses`            | 60/min       |
| `POST /api/expenses`           | 30/min       |
| `PUT /api/expenses/:id`        | 30/min       |
| `DELETE /api/expenses/:id`     | 20/min       |
| `GET /api/expenses/summary`    | 30/min       |
| `POST /api/upload`             | 10/min       |

---

## Project Structure

```
expense-tracker/
├── app/
│   ├── __init__.py         # App factory, extensions init
│   ├── models.py           # SQLAlchemy Expense model
│   └── routes/
│       ├── main.py         # Index page + health check
│       ├── expenses.py     # CRUD + summary API
│       └── uploads.py      # S3 upload + Textract OCR
├── app/templates/
│   └── index.html          # Full SPA dashboard frontend
├── .github/
│   └── workflows/
│       └── deploy.yml      # GitHub Actions CI/CD
├── Dockerfile              # Multi-stage production image
├── docker-compose.yml      # Local dev with Postgres
├── requirements.txt
├── run.py                  # App entrypoint
├── .env.example
└── README.md
```
