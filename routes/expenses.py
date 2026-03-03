"""Expenses routes"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.database import get_db, login_required, admin_required, log_activity

expenses_bp = Blueprint('expenses', __name__)


@expenses_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    conn = get_db()
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            category = request.form.get('category')
            amount = float(request.form.get('amount', 0))
            description = request.form.get('description', '')
            expense_date = request.form.get('expense_date')
            
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO expenses (title, category, amount, description, expense_date, added_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (title, category, amount, description, expense_date, session['user_id']))
            conn.commit()
            log_activity(session['user_id'], 'ADD_EXPENSE', 'expenses', f"Added expense: {title}", request.remote_addr)
            flash('Expense added successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash('Error adding expense.', 'danger')
            print(f"Expense error: {e}")
    
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT e.*, u.full_name as added_by_name
                FROM expenses e JOIN users u ON e.added_by = u.id
                ORDER BY e.expense_date DESC LIMIT 50
            """)
            expenses = cursor.fetchall()
            
            cursor.execute("""
                SELECT category, COALESCE(SUM(amount), 0) as total
                FROM expenses WHERE MONTH(expense_date) = MONTH(CURDATE())
                GROUP BY category
            """)
            by_category = cursor.fetchall()
            
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as monthly_total 
                FROM expenses WHERE MONTH(expense_date) = MONTH(CURDATE())
                AND YEAR(expense_date) = YEAR(CURDATE())
            """)
            monthly_total = cursor.fetchone()['monthly_total']
    except Exception as e:
        print(f"Expenses load error: {e}")
        expenses = []
        by_category = []
        monthly_total = 0
    finally:
        conn.close()
    
    return render_template('expenses/index.html', expenses=expenses,
                         by_category=by_category, monthly_total=monthly_total)
