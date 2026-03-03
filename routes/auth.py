"""Authentication routes"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import bcrypt
from models.database import get_db, log_activity

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter username and password.', 'danger')
            return render_template('auth/login.html')
        
        try:
            conn = get_db()
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM users WHERE username = %s AND is_active = TRUE",
                    (username,)
                )
                user = cursor.fetchone()
            
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['full_name'] = user['full_name']
                session['role'] = user['role']
                
                # Update last login
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE users SET last_login = NOW() WHERE id = %s",
                        (user['id'],)
                    )
                conn.commit()
                
                log_activity(user['id'], 'LOGIN', 'auth', f"User {username} logged in", 
                           request.remote_addr)
                
                flash(f'Welcome back, {user["full_name"]}!', 'success')
                return redirect(url_for('dashboard.index'))
            else:
                flash('Invalid username or password.', 'danger')
                log_activity(None, 'FAILED_LOGIN', 'auth', f"Failed login for {username}",
                           request.remote_addr)
            
            conn.close()
        except Exception as e:
            flash('Database error. Please try again.', 'danger')
            print(f"Login error: {e}")
    
    return render_template('auth/login.html')


@auth_bp.route('/logout')
def logout():
    user_id = session.get('user_id')
    username = session.get('username')
    if user_id:
        log_activity(user_id, 'LOGOUT', 'auth', f"User {username} logged out",
                    request.remote_addr)
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))
