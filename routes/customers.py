"""Customers routes"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.database import get_db, login_required

customers_bp = Blueprint('customers', __name__)


@customers_bp.route('/')
@login_required
def index():
    conn = get_db()
    search = request.args.get('search', '')
    page = int(request.args.get('page', 1))
    per_page = 15
    offset = (page - 1) * per_page
    
    try:
        with conn.cursor() as cursor:
            query = "SELECT * FROM customers WHERE 1=1"
            params = []
            if search:
                query += " AND (name LIKE %s OR phone LIKE %s)"
                params.extend([f'%{search}%', f'%{search}%'])
            
            cursor.execute(f"SELECT COUNT(*) as cnt FROM customers WHERE 1=1 {'AND (name LIKE %s OR phone LIKE %s)' if search else ''}", params)
            total = cursor.fetchone()['cnt']
            
            query += " ORDER BY total_spent DESC LIMIT %s OFFSET %s"
            params.extend([per_page, offset])
            cursor.execute(query, params)
            customers = cursor.fetchall()
    except Exception as e:
        print(f"Customers error: {e}")
        customers = []
        total = 0
    finally:
        conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    return render_template('customers/index.html', customers=customers, search=search,
                         page=page, total_pages=total_pages, total=total)


@customers_bp.route('/view/<int:customer_id>')
@login_required
def view_customer(customer_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
            customer = cursor.fetchone()
            
            if not customer:
                flash('Customer not found.', 'danger')
                return redirect(url_for('customers.index'))
            
            cursor.execute("""
                SELECT o.*, p.payment_status, p.payment_method
                FROM orders o
                LEFT JOIN payments p ON p.order_id = o.id
                WHERE o.customer_id = %s
                ORDER BY o.created_at DESC
            """, (customer_id,))
            orders = cursor.fetchall()
    except Exception as e:
        print(f"Customer view error: {e}")
        customer = None
        orders = []
    finally:
        conn.close()
    
    return render_template('customers/view.html', customer=customer, orders=orders)
