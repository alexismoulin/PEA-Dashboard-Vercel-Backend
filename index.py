"""Vercel Python Function: authenticated market prices only."""
import os
import re
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import auth
from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
origin = os.environ.get("ALLOWED_ORIGIN", "http://localhost:5173").rstrip("/")
CORS(app, resources={r"/api/*": {"origins": [origin]}})

def authenticated_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={
                "projectId": os.environ["FIREBASE_PROJECT_ID"]
            })
        user = auth.verify_id_token(header[7:])
        allowed = os.environ.get("ALLOWED_EMAIL", "").strip().lower()
        if allowed and (
            not user.get("email_verified")
            or user.get("email", "").lower() != allowed
        ):
            return None
        return user
    except (ValueError, KeyError, Exception):
        return None

@app.get("/health")
def health():
    return jsonify({"ok": True})

@app.post("/api/prices")
def prices():
    if not authenticated_user():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("tickers"), list):
        return jsonify({"error": "Expected tickers array"}), 400
    tickers = data["tickers"]
    if (not tickers or len(tickers) > 50 or
        any(not isinstance(t, str) or not re.fullmatch(r"[A-Za-z0-9^.=\-]{1,24}", t)
            for t in tickers)):
        return jsonify({"error": "Invalid tickers"}), 400
    unique = list(dict.fromkeys(tickers))
    prices, errors = {}, []
    for ticker in unique:
        try:
            history = yf.Ticker(ticker).history(period="5d", auto_adjust=False)
            if history.empty:
                raise ValueError("No price available")
            close = history["Close"].dropna()
            if close.empty:
                raise ValueError("No closing price available")
            prices[ticker] = float(close.iloc[-1])
        except Exception:
            errors.append({"ticker": ticker, "error": "Price unavailable"})
    return jsonify({
        "prices": prices,
        "errors": errors,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
