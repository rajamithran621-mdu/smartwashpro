"""Reports routes"""
from flask import Blueprint, render_template, request
from models.database import get_db, login_required, admin_required
from datetime import datetime, date, timedelta

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/')
@login_required
def index():
    report_type = request.args.get('type', 'daily')
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    
    conn = get_db()
    data = {}
    
    try:
        with conn.cursor() as cursor:
            if report_type == 'daily':
                # Daily report
                cursor.execute("""
                    SELECT COUNT(*) as total_orders, 
                           COALESCE(SUM(o.final_amount), 0) as total_revenue,
                           COALESCE(SUM(CASE WHEN o.status='delivered' THEN o.final_amount ELSE 0 END), 0) as collected
                    FROM orders o WHERE DATE(o.created_at) = %s
                """, (selected_date,))
                data['summary'] = cursor.fetchone()
                
                cursor.execute("""
                    SELECT o.*, c.name as customer_name, c.phone
                    FROM orders o JOIN customers c ON o.customer_id = c.id
                    WHERE DATE(o.created_at) = %s ORDER BY o.created_at
                """, (selected_date,))
                data['orders'] = cursor.fetchall()
                
                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) as expenses FROM expenses WHERE expense_date = %s
                """, (selected_date,))
                data['expenses'] = cursor.fetchone()['expenses']
                
            elif report_type == 'monthly':
                month = request.args.get('month', date.today().strftime('%Y-%m'))
                year, mon = month.split('-')
                
                cursor.execute("""
                    SELECT DATE(created_at) as day, COUNT(*) as orders, 
                           COALESCE(SUM(final_amount), 0) as revenue
                    FROM orders WHERE YEAR(created_at)=%s AND MONTH(created_at)=%s
                    GROUP BY DATE(created_at) ORDER BY day
                """, (year, mon))
                data['daily_breakdown'] = cursor.fetchall()
                
                cursor.execute("""
                    SELECT service_type, COUNT(*) as count, COALESCE(SUM(final_amount), 0) as revenue
                    FROM orders WHERE YEAR(created_at)=%s AND MONTH(created_at)=%s
                    GROUP BY service_type
                """, (year, mon))
                data['by_service'] = cursor.fetchall()
                
                cursor.execute("""
                    SELECT COALESCE(SUM(final_amount), 0) as total_revenue,
                           COUNT(*) as total_orders
                    FROM orders WHERE YEAR(created_at)=%s AND MONTH(created_at)=%s
                """, (year, mon))
                data['summary'] = cursor.fetchone()
                
                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) as expenses 
                    FROM expenses WHERE YEAR(expense_date)=%s AND MONTH(expense_date)=%s
                """, (year, mon))
                data['expenses'] = cursor.fetchone()['expenses']
                data['month'] = month
                
            elif report_type == 'weekly':
                start = date.today() - timedelta(days=date.today().weekday())
                end = start + timedelta(days=6)
                
                cursor.execute("""
                    SELECT DAYNAME(created_at) as day, COUNT(*) as orders, 
                           COALESCE(SUM(final_amount), 0) as revenue
                    FROM orders WHERE DATE(created_at) BETWEEN %s AND %s
                    GROUP BY DATE(created_at), DAYNAME(created_at)
                    ORDER BY DATE(created_at)
                """, (start, end))
                data['weekly'] = cursor.fetchall()
                
                cursor.execute("""
                    SELECT COALESCE(SUM(final_amount), 0) as total_revenue, COUNT(*) as total_orders
                    FROM orders WHERE DATE(created_at) BETWEEN %s AND %s
                """, (start, end))
                data['summary'] = cursor.fetchone()
                data['start'] = start
                data['end'] = end
                
    except Exception as e:
        print(f"Reports error: {e}")
    finally:
        conn.close()
    
    return render_template('reports/index.html', data=data, report_type=report_type,
                         selected_date=selected_date)
