from datetime import datetime
from app import db


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    merchant = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    category = db.Column(db.String(100), nullable=False, default="Uncategorized")
    description = db.Column(db.Text, nullable=True)
    receipt_url = db.Column(db.String(500), nullable=True)   # S3 object URL
    raw_ocr_text = db.Column(db.Text, nullable=True)          # raw Textract output
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "merchant": self.merchant,
            "amount": float(self.amount),
            "date": self.date.isoformat(),
            "category": self.category,
            "description": self.description,
            "receipt_url": self.receipt_url,
            "created_at": self.created_at.isoformat(),
        }
