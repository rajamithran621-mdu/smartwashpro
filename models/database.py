"""
Database connection and utility functions
PostgreSQL (Render) compatible version
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from functools import wraps
from flask import session, redirect, url_for, flash


# ---------- DATABASE CONNECTION ----------
def get_db():
    """
    Get a PostgreSQL database connection using DATABASE_URL
    """
    DATABASE_URL = os.environ.get("DATABASE_URL")

    if not DATABASE_URL:
        raise Exception("DATABASE_URL environment variable not set")

    conn = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=RealDictCursor
    )
    return conn


# ---------- LOGIN REQUIRED DECORATOR ----------
def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# ---------- ADMIN REQUIRED DECORATOR ----------
def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated_function


# ---------- LOG ACTIVITY ----------
def log_activity(user_id, action, module, description='', ip_address=''):
    """Log user activity into logs table."""
    try:
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO logs (user_id, action, module, description, ip_address)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, action, module, description, ip_address)
        )

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Log error: {e}")
