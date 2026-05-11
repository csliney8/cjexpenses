import boto3
from flask import Blueprint, jsonify, request, current_app, redirect
from flask_login import login_required, current_user
from datetime import datetime, date
from sqlalchemy import extract, func
from app import db, limiter
from app.models import Expense

expenses_bp = Blueprint("expenses", __name__)

VALID_CATEGORIES = [
    "Food & Dining", "Transportation", "Shopping", "Entertainment",
    "Health & Medical", "Housing", "Utilities", "Travel", "Education",
    "Business", "Personal Care", "Uncategorized",
]


# List / filter expenses (only this user's)
@expenses_bp.route("/expenses", methods=["GET"])
@login_required
@limiter.limit("60 per minute")
def get_expenses():
    query = Expense.query.filter_by(user_id=current_user.id)

    category = request.args.get("category")
    month = request.args.get("month")
    start = request.args.get("start")
    end = request.args.get("end")

    if category:
        query = query.filter_by(category=category)
    if month:
        try:
            year, mo = map(int, month.split("-"))
            query = query.filter(
                extract("year", Expense.date) == year,
                extract("month", Expense.date) == mo,
            )
        except ValueError:
            return jsonify({"error": "month must be YYYY-MM"}), 400
    if start:
        try:
            query = query.filter(Expense.date >= date.fromisoformat(start))
        except ValueError:
            return jsonify({"error": "start must be YYYY-MM-DD"}), 400
    if end:
        try:
            query = query.filter(Expense.date <= date.fromisoformat(end))
        except ValueError:
            return jsonify({"error": "end must be YYYY-MM-DD"}), 400

    expenses = query.order_by(Expense.date.desc()).all()
    return jsonify([e.to_dict() for e in expenses])


# Create expense manually (assigned to current user)
@expenses_bp.route("/expenses", methods=["POST"])
@login_required
@limiter.limit("30 per minute")
def create_expense():
    data = request.get_json(force=True)
    required = ["merchant", "amount", "date"]
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        expense_date = date.fromisoformat(data["date"])
        amount = float(data["amount"])
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date or amount"}), 400

    expense = Expense(
        user_id=current_user.id,
        merchant=data["merchant"].strip(),
        amount=amount,
        date=expense_date,
        category=data.get("category", "Uncategorized"),
        description=data.get("description", ""),
    )
    db.session.add(expense)
    db.session.commit()
    return jsonify(expense.to_dict()), 201


# Get single expense (only if owned by current user)
@expenses_bp.route("/expenses/<int:expense_id>", methods=["GET"])
@login_required
@limiter.limit("60 per minute")
def get_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    return jsonify(expense.to_dict())


# Update expense (only if owned by current user)
@expenses_bp.route("/expenses/<int:expense_id>", methods=["PUT"])
@login_required
@limiter.limit("30 per minute")
def update_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    data = request.get_json(force=True)

    if "merchant" in data:
        expense.merchant = data["merchant"].strip()
    if "amount" in data:
        try:
            expense.amount = float(data["amount"])
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid amount"}), 400
    if "date" in data:
        try:
            expense.date = date.fromisoformat(data["date"])
        except ValueError:
            return jsonify({"error": "Invalid date"}), 400
    if "category" in data:
        expense.category = data["category"]
    if "description" in data:
        expense.description = data["description"]

    expense.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(expense.to_dict())


# Generate a short-lived presigned S3 URL for the receipt image
@expenses_bp.route("/expenses/<int:expense_id>/receipt", methods=["GET"])
@login_required
@limiter.limit("60 per minute")
def get_receipt(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    if not expense.receipt_url:
        return jsonify({"error": "No receipt for this expense"}), 404

    bucket = current_app.config.get("S3_BUCKET", "")
    if not bucket:
        return jsonify({"error": "S3_BUCKET not configured"}), 500

    marker = ".amazonaws.com/"
    if marker not in expense.receipt_url:
        return jsonify({"error": "Invalid receipt URL"}), 500
    key = expense.receipt_url.split(marker, 1)[1]

    s3 = boto3.client("s3", region_name=current_app.config["AWS_REGION"])
    try:
        presigned = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=300,
        )
    except Exception as exc:
        return jsonify({"error": f"Failed to generate URL: {str(exc)}"}), 500

    return redirect(presigned)


# Delete expense (only if owned by current user)
@expenses_bp.route("/expenses/<int:expense_id>", methods=["DELETE"])
@login_required
@limiter.limit("20 per minute")
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=current_user.id).first_or_404()
    db.session.delete(expense)
    db.session.commit()
    return jsonify({"message": "Deleted", "id": expense_id})


# Summary / analytics (scoped to current user)
@expenses_bp.route("/expenses/summary", methods=["GET"])
@login_required
@limiter.limit("30 per minute")
def get_summary():
    base = Expense.query.filter_by(user_id=current_user.id)

    total = (
        db.session.query(func.sum(Expense.amount))
        .filter(Expense.user_id == current_user.id)
        .scalar() or 0
    )
    count = base.count()

    by_category = (
        db.session.query(Expense.category, func.sum(Expense.amount).label("total"))
        .filter(Expense.user_id == current_user.id)
        .group_by(Expense.category)
        .all()
    )

    monthly = (
        db.session.query(
            extract("year", Expense.date).label("year"),
            extract("month", Expense.date).label("month"),
            func.sum(Expense.amount).label("total"),
        )
        .filter(Expense.user_id == current_user.id)
        .group_by("year", "month")
        .order_by("year", "month")
        .limit(12)
        .all()
    )

    return jsonify({
        "total": float(total),
        "count": count,
        "by_category": [{"category": r[0], "total": float(r[1])} for r in by_category],
        "monthly": [
            {"year": int(r.year), "month": int(r.month), "total": float(r.total)}
            for r in monthly
        ],
    })
