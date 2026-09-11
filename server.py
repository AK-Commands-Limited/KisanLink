"""Private backend for the farmer marketplace web interface.

Run with: python server.py
The Excel price workbook stays server-side; only filtered price results are returned.
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).parent
DATA_DIR = Path(os.getenv("APP_DATA_DIR", ROOT))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / "marketplace.db"
PRICE_FILE = ROOT / "Market_prices.csv.xlsx"
USER_FILE = DATA_DIR / "User_info.xlsx"
app = Flask(__name__)
app.config.update(SECRET_KEY=os.getenv("AGRI_SECRET_KEY", secrets.token_urlsafe(32)), SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE="Lax")


def connection():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with connection() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
          name TEXT, business_name TEXT, phone TEXT, location TEXT, farm_info TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS listings (
          id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, product_name TEXT NOT NULL, commodity TEXT NOT NULL,
          variety TEXT, quantity REAL NOT NULL, unit TEXT NOT NULL, asking_price REAL NOT NULL,
          location TEXT, harvest_date TEXT, description TEXT, delivery TEXT, available INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY, listing_id INTEGER NOT NULL, buyer_id INTEGER NOT NULL, quantity REAL NOT NULL,
          created_at TEXT NOT NULL, FOREIGN KEY(listing_id) REFERENCES listings(id), FOREIGN KEY(buyer_id) REFERENCES users(id));
        """)
    ensure_user_workbook()


USER_COLUMNS = ["user_id", "username", "password_hash", "name", "business_name", "phone", "location", "farm_info", "created_at", "record_reference"]


def users_frame():
    if not USER_FILE.exists():
        return pd.DataFrame(columns=USER_COLUMNS)
    return pd.read_excel(USER_FILE, sheet_name="Users", dtype=str).fillna("")


def save_users(frame):
    # This workbook is a private backend file: it is never served by Flask.
    frame.to_excel(USER_FILE, sheet_name="Users", index=False)


def ensure_user_workbook():
    if not USER_FILE.exists():
        # Local/deployment starter account; replace it after first sign-in.
        save_users(pd.DataFrame([["test-farmer-001", "test_farmer", generate_password_hash("Farmer@123"), "Test Farmer", "", "", "", "", datetime.now(timezone.utc).isoformat(), "SE-20260911-TEST_FARMER"]], columns=USER_COLUMNS))


def user():
    return session.get("user_id")


def require_login(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not user(): return jsonify(error="Please log in to use this feature."), 401
        return fn(*args, **kwargs)
    return wrapped


def price_data():
    # Cached after the first request; the workbook never becomes a public static asset.
    if not hasattr(price_data, "frame"):
        df = pd.read_excel(PRICE_FILE, sheet_name="Market_prices")
        df["arrival_date"] = pd.to_datetime(df["arrival_date"])
        price_data.frame = df
    return price_data.frame


def reference_price(commodity, variety=None, location=None):
    df = price_data()
    rows = df[df.commodity.astype(str).str.casefold() == str(commodity).casefold()]
    if variety: rows = rows[rows.variety.astype(str).str.casefold() == str(variety).casefold()]
    if rows.empty: return None
    row = rows.sort_values("arrival_date").iloc[-1]
    return {"modal_price": float(row.modal_price), "market": row.market, "arrival_date": row.arrival_date.strftime("%d %b %Y")}


@app.get("/")
def home(): return send_from_directory(ROOT, "index.html")


@app.get("/api/filters")
def filters():
    df = price_data(); key = request.args.get("key", "state"); selected = request.args.get("selected", "")
    hierarchy = ["state", "district", "market", "commodity", "variety"]
    if key not in hierarchy: return jsonify(error="Unknown filter."), 400
    for column in hierarchy[:hierarchy.index(key)]:
        value = selected.split("|")[hierarchy.index(column)] if "|" in selected else request.args.get(column)
        if value: df = df[df[column] == value]
    return jsonify(sorted(str(x) for x in df[key].dropna().unique()))


@app.get("/api/prices")
def prices():
    df = price_data()
    needed = ["state", "district", "market", "commodity", "variety"]
    values = {key: request.args.get(key, "") for key in needed}
    if not all(values.values()): return jsonify(error="Choose every filter first."), 400
    for key, value in values.items(): df = df[df[key] == value]
    df = df.sort_values("arrival_date")
    if df.empty: return jsonify(error="No records for this combination."), 404
    latest = df.iloc[-1]
    return jsonify(latest={"modal": float(latest.modal_price), "min": float(latest.min_price), "max": float(latest.max_price)},
                   timeline=[{"date": r.arrival_date.strftime("%Y-%m-%d"), "modal": float(r.modal_price)} for _, r in df.iterrows()],
                   records=[{"date": r.arrival_date.strftime("%d %b %Y"), "grade": r.grade, "min": float(r.min_price), "max": float(r.max_price), "modal": float(r.modal_price)} for _, r in df.iterrows()])


@app.post("/api/auth/setup")
def setup():
    data = request.get_json() or {}
    username, password = data.get("username", "").strip(), data.get("password", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", username) or len(password) < 8: return jsonify(error="Use a 3–32 character username and an 8+ character password."), 400
    users = users_frame()
    if not users.empty: return jsonify(error="Initial setup is already complete. Log in with an existing account."), 409
    uid = str(uuid.uuid4())
    users.loc[len(users)] = [uid, username, generate_password_hash(password), data.get("name", "").strip(), "", "", "", "", datetime.now(timezone.utc).isoformat(), f"SE-{datetime.now():%Y%m%d}-{username.upper()}"]
    save_users(users)
    session["user_id"] = uid
    return jsonify(ok=True)


@app.post("/api/auth/login")
def login():
    data = request.get_json() or {}; username = data.get("username", "").strip()
    rows = users_frame(); match = rows[rows.username.str.casefold() == username.casefold()]
    if match.empty: return jsonify(error="Username not found."), 401
    row = match.iloc[0]
    if not check_password_hash(row["password_hash"], data.get("password", "")): return jsonify(error="Wrong password."), 401
    session.clear(); session["user_id"] = row["user_id"]
    return jsonify(ok=True)


@app.post("/api/auth/logout")
def logout(): session.clear(); return jsonify(ok=True)


@app.get("/api/me")
def me():
    if not user(): return jsonify(authenticated=False)
    rows = users_frame(); match = rows[rows.user_id == user()]
    if match.empty: session.clear(); return jsonify(authenticated=False)
    row = match.iloc[0].to_dict()
    return jsonify(authenticated=True, user={"id": row["user_id"], "username": row["username"], "name": row["name"], "business_name": row["business_name"], "phone": row["phone"], "location": row["location"], "farm_info": row["farm_info"], "record_reference": row["record_reference"]})


@app.put("/api/profile")
@require_login
def profile():
    data = request.get_json() or {}; fields = ["name", "business_name", "phone", "location", "farm_info"]
    users = users_frame(); mask = users.user_id == user()
    if not mask.any(): return jsonify(error="Account not found."), 404
    for field in fields: users.loc[mask, field] = str(data.get(field, "")).strip()
    save_users(users)
    return jsonify(ok=True, reference=users.loc[mask, "record_reference"].iloc[0])


@app.get("/api/listings")
def listings():
    q = request.args.get("q", "").strip(); mine = request.args.get("mine") == "1"
    sql = "SELECT l.* FROM listings l WHERE l.available=1"; args=[]
    if mine:
        if not user(): return jsonify(error="Log in first."), 401
        sql = sql.replace("WHERE l.available=1", "WHERE l.user_id=?"); args.append(user())
    if q: sql += " AND (l.product_name LIKE ? OR l.commodity LIKE ? OR l.variety LIKE ? OR l.location LIKE ?)"; args += [f"%{q}%"] * 4
    with connection() as db: rows=[dict(r) for r in db.execute(sql + " ORDER BY l.created_at DESC", args).fetchall()]
    users = users_frame().set_index("user_id").to_dict("index")
    for r in rows:
        farmer = users.get(r["user_id"], {})
        r["name"] = farmer.get("name", "")
        r["business_name"] = farmer.get("business_name", "")
        r["farmer_location"] = farmer.get("location", "")
        r["reference"] = reference_price(r["commodity"], r["variety"], r["location"])
    return jsonify(rows)


@app.post("/api/listings")
@require_login
def add_listing():
    d=request.get_json() or {}; required=["product_name","commodity","quantity","unit","asking_price"]
    if any(not str(d.get(x, "")).strip() for x in required): return jsonify(error="Complete all required listing fields."), 400
    try: quantity=float(d["quantity"]); price=float(d["asking_price"]); assert quantity > 0 and price > 0
    except (ValueError, AssertionError): return jsonify(error="Quantity and price must be positive numbers."), 400
    fields=["product_name","commodity","variety","unit","location","harvest_date","description","delivery"]
    with connection() as db:
        db.execute("INSERT INTO listings(user_id,"+",".join(fields)+",quantity,asking_price,created_at) VALUES("+",".join(["?"]*(len(fields)+4))+")", [user()]+[str(d.get(x," ")).strip() for x in fields]+[quantity,price,datetime.now(timezone.utc).isoformat()])
    return jsonify(ok=True)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")


# Gunicorn imports this module rather than executing __main__.
init_db()
