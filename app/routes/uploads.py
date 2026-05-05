import os
import uuid
import re
import boto3
from datetime import date
from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename
from app import db, limiter
from app.models import Expense

uploads_bp = Blueprint("uploads", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "tiff"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_s3_client():
    return boto3.client("s3", region_name=current_app.config["AWS_REGION"])


def get_textract_client():
    return boto3.client("textract", region_name=current_app.config["AWS_REGION"])


def parse_textract_response(response):
    """
    Pull merchant, amount, and date hints from raw Textract LINE blocks.
    Returns a dict with best-effort extracted fields.
    """
    lines = [
        block["Text"]
        for block in response.get("Blocks", [])
        if block["BlockType"] == "LINE"
    ]
    raw_text = "\n".join(lines)

    # ── Amount: look for dollar amounts, take the largest (likely the total) ──
    amounts = re.findall(r"\$?\s?(\d{1,4}[.,]\d{2})", raw_text)
    amount = max([float(a.replace(",", "")) for a in amounts], default=None) if amounts else None

    # ── Date: common formats ──────────────────────────────────────────────────
    date_patterns = [
        r"\b(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})\b",
        r"\b([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})\b",
    ]
    detected_date = None
    for pat in date_patterns:
        m = re.search(pat, raw_text)
        if m:
            detected_date = m.group(1)
            break

    # ── Merchant: first non-blank line is usually the store name ─────────────
    merchant = next((l.strip() for l in lines if len(l.strip()) > 2), "Unknown Merchant")

    return {
        "merchant": merchant[:255],
        "amount": amount,
        "date_hint": detected_date,
        "raw_text": raw_text,
    }


# ── Upload receipt → S3 → Textract → RDS ─────────────────────────────────────
@uploads_bp.route("/upload", methods=["POST"])
@limiter.limit("10 per minute")
def upload_receipt():
    bucket = current_app.config.get("S3_BUCKET", "")
    if not bucket:
        return jsonify({"error": "S3_BUCKET not configured on server"}), 500

    if "file" not in request.files:
        return jsonify({"error": "No file field in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # ── 1. Upload to S3 ───────────────────────────────────────────────────────
    filename = secure_filename(file.filename)
    key = f"receipts/{uuid.uuid4()}_{filename}"

    s3 = get_s3_client()
    try:
        s3.upload_fileobj(
            file,
            bucket,
            key,
            ExtraArgs={"ContentType": file.content_type},
        )
    except Exception as exc:
        return jsonify({"error": f"S3 upload failed: {str(exc)}"}), 500

    receipt_url = f"https://{bucket}.s3.amazonaws.com/{key}"

    # ── 2. Run Textract OCR on the uploaded object ─────────────────────────
    textract = get_textract_client()
    try:
        response = textract.detect_document_text(
            Document={"S3Object": {"Bucket": bucket, "Name": key}}
        )
    except Exception as exc:
        # Still save the expense — just without parsed data
        expense = Expense(
            merchant="Unknown (OCR failed)",
            amount=0.00,
            date=date.today(),
            category="Uncategorized",
            receipt_url=receipt_url,
            raw_ocr_text=f"Textract error: {str(exc)}",
        )
        db.session.add(expense)
        db.session.commit()
        return jsonify({
            "warning": "OCR failed; expense saved with placeholder values.",
            "expense": expense.to_dict(),
        }), 201

    # ── 3. Parse the OCR output ───────────────────────────────────────────────
    parsed = parse_textract_response(response)

    # Resolve date string to a date object
    expense_date = date.today()
    if parsed["date_hint"]:
        for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
            try:
                expense_date = date.strptime(parsed["date_hint"], fmt)  # type: ignore[attr-defined]
                break
            except ValueError:
                continue
        else:
            # datetime.strptime is on datetime, not date
            from datetime import datetime as dt
            for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%B %d %Y"):
                try:
                    expense_date = dt.strptime(parsed["date_hint"], fmt).date()
                    break
                except ValueError:
                    continue

    # ── 4. Save parsed expense to RDS ─────────────────────────────────────────
    expense = Expense(
        merchant=parsed["merchant"],
        amount=parsed["amount"] or 0.00,
        date=expense_date,
        category=request.form.get("category", "Uncategorized"),
        description=request.form.get("description", ""),
        receipt_url=receipt_url,
        raw_ocr_text=parsed["raw_text"],
    )
    db.session.add(expense)
    db.session.commit()

    return jsonify({
        "message": "Receipt processed and expense saved.",
        "expense": expense.to_dict(),
        "ocr_preview": parsed["raw_text"][:300],
    }), 201
