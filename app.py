import os
import sqlite3
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Set SECRET_KEY as an environment variable in real deployments.
# The random fallback is fine for local development (logins reset on restart).
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# Always use the database.db that sits next to app.py, no matter where you run it from
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


# ---------- Database helpers ----------

def get_db():
    """One connection per request, reused and closed automatically."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables automatically on first run.

    users          -> login accounts (Task 2): username + hashed password
    managed_users  -> the name/email records managed on the dashboard (Task 1)
    """
    conn = sqlite3.connect(DB_PATH)

    # If an old Task 1 database is reused, its `users` table (name/email) would
    # clash with the new login `users` table. Rename it instead of losing data.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
    if cols and "username" not in cols and "email" in cols:
        conn.execute("ALTER TABLE users RENAME TO managed_users")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS managed_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        )
        """
    )
    conn.commit()
    conn.close()


# ---------- Access control ----------

def login_required(view):
    """Put @login_required under @app.route to protect any page."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session:
            flash("Please log in to access that page.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ---------- Authentication routes ----------

@app.route("/")
def home():
    return redirect(url_for("dashboard" if "user" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        raw_password = request.form["password"]

        if len(username) < 3:
            flash("Username must be at least 3 characters.", "error")
            return render_template("register.html")
        if len(raw_password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, generate_password_hash(raw_password)),
            )
            db.commit()
        except sqlite3.IntegrityError:  # UNIQUE constraint on username
            flash("That username is already taken.", "error")
            return render_template("register.html")

        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user"] = user["username"]
            return redirect(url_for("dashboard"))

        # Same message for wrong username or wrong password (don't leak which)
        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------- Protected page: Task 1's user management lives here now ----------

@app.route("/dashboard", methods=["GET", "POST"])
@login_required
def dashboard():
    db = get_db()

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()

        if not name or not email:
            flash("Name and email are required.", "error")
            return redirect(url_for("dashboard"))

        try:
            db.execute(
                "INSERT INTO managed_users (name, email) VALUES (?, ?)", (name, email)
            )
            db.commit()
            flash(f"User '{name}' added successfully.", "success")
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "error")
        return redirect(url_for("dashboard"))

    users = db.execute("SELECT * FROM managed_users ORDER BY id DESC").fetchall()
    return render_template("dashboard.html", user=session["user"], users=users)


init_db()

if __name__ == "__main__":
    app.run(debug=True)
