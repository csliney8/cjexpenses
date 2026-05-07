from flask import Blueprint, jsonify, request
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


# ── List / filter expenses ────────────────────────────────────────────────────
@expenses_bp.route("/expenses", methods=["GET"])
@limiter.limit("60 per minute")
def get_expenses():
    query = Expense.query

    # Optional filters
    category = request.args.get("category")
    month = request.args.get("month")   # expects YYYY-MM
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


# ── Create expense manually ───────────────────────────────────────────────────
@expenses_bp.route("/expenses", methods=["POST"])
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
        merchant=data["merchant"].strip(),
        amount=amount,
        date=expense_date,
        category=data.get("category", "Uncategorized"),
        description=data.get("description", ""),
    )
    db.session.add(expense)
    db.session.commit()
    return jsonify(expense.to_dict()), 201


# ── Get single expense ────────────────────────────────────────────────────────
@expenses_bp.route("/expenses/<int:expense_id>", methods=["GET"])
@limiter.limit("60 per minute")
def get_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    return jsonify(expense.to_dict())


# ── Update expense ────────────────────────────────────────────────────────────
@expenses_bp.route("/expenses/<int:expense_id>", methods=["PUT"])
@limiter.limit("30 per minute")
def update_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
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


# ── Delete expense ────────────────────────────────────────────────────────────
@expenses_bp.route("/expenses/<int:expense_id>", methods=["DELETE"])
@limiter.limit("20 per minute")
def delete_expense(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    db.session.delete(expense)
    db.session.commit()
    return jsonify({"message": "Deleted", "id": expense_id})


# ── Summary / analytics ────────────────────────────────────────────────────────
@expenses_bp.route("/expenses/summary", methods=["GET"])
@limiter.limit("30 per minute")
def get_summary():
    # Total and count
    total = db.session.query(func.sum(Expense.amount)).scalar() or 0
    count = Expense.query.count()

    # By category
    by_category = (
        db.session.query(Expense.category, func.sum(Expense.amount).label("total"))
        .group_by(Expense.category)
        .all()
    )

    # Monthly totals (last 6 months)
    monthly = (
        db.session.query(
            extract("year", Expense.date).label("year"),
            extract("month", Expense.date).label("month"),
            func.sum(Expense.amount).label("total"),
        )
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
