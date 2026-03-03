"""Dashboard routes"""
from flask import Blueprint, render_template, session
from models.database import get_db, login_required
from datetime import datetime, date

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/dashboard')
@login_required
def index():
    conn = get_db()
    stats = {}
    
    try:
        with conn.cursor() as cursor:
            today = date.today().strftime('%Y-%m-%d')
            
            # Today's orders
            cursor.execute("SELECT COUNT(*) as count FROM orders WHERE DATE(created_at) = %s", (today,))
            stats['today_orders'] = cursor.fetchone()['count']
            
            # Pending orders
            cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status IN ('pending', 'processing')")
            stats['pending_orders'] = cursor.fetchone()['count']
            
            # Completed orders
            cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'delivered'")
            stats['completed_orders'] = cursor.fetchone()['count']
            
            # Ready orders
            cursor.execute("SELECT COUNT(*) as count FROM orders WHERE status = 'ready'")
            stats['ready_orders'] = cursor.fetchone()['count']
            
            # Today's revenue
            cursor.execute("""
                SELECT COALESCE(SUM(p.amount), 0) as revenue 
                FROM payments p 
                WHERE DATE(p.paid_at) = %s AND p.payment_status = 'paid'
            """, (today,))
            stats['today_revenue'] = cursor.fetchone()['revenue']
            
            # Monthly revenue
            cursor.execute("""
                SELECT COALESCE(SUM(p.amount), 0) as revenue 
                FROM payments p 
                WHERE MONTH(p.paid_at) = MONTH(CURDATE()) 
                AND YEAR(p.paid_at) = YEAR(CURDATE())
                AND p.payment_status = 'paid'
            """)
            stats['monthly_revenue'] = cursor.fetchone()['revenue']
            
            # Total customers
            cursor.execute("SELECT COUNT(*) as count FROM customers")
            stats['total_customers'] = cursor.fetchone()['count']
            
            # Recent orders
            cursor.execute("""
                SELECT o.*, c.name as customer_name, c.phone 
                FROM orders o 
                JOIN customers c ON o.customer_id = c.id 
                ORDER BY o.created_at DESC LIMIT 8
            """)
            recent_orders = cursor.fetchall()
            
            # Monthly revenue chart data (last 6 months)
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(paid_at, '%b %Y') as month,
                    MONTH(paid_at) as month_num,
                    YEAR(paid_at) as year_num,
                    COALESCE(SUM(amount), 0) as total
                FROM payments 
                WHERE payment_status = 'paid' 
                AND paid_at >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                GROUP BY YEAR(paid_at), MONTH(paid_at)
                ORDER BY year_num, month_num
            """)
            chart_data = cursor.fetchall()
            
            # Order status distribution
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM orders 
                GROUP BY status
            """)
            status_data = cursor.fetchall()
            
            # Recent activity logs
            cursor.execute("""
                SELECT l.*, u.full_name 
                FROM logs l 
                LEFT JOIN users u ON l.user_id = u.id 
                ORDER BY l.created_at DESC LIMIT 10
            """)
            activity_logs = cursor.fetchall()
            
            # Staff activity
            cursor.execute("""
                SELECT u.full_name, COUNT(o.id) as order_count
                FROM users u
                LEFT JOIN orders o ON o.created_by = u.id AND DATE(o.created_at) = %s
                WHERE u.role = 'staff' OR u.role = 'admin'
                GROUP BY u.id
            """, (today,))
            staff_activity = cursor.fetchall()
            
    except Exception as e:
        print(f"Dashboard error: {e}")
        recent_orders = []
        chart_data = []
        status_data = []
        activity_logs = []
        staff_activity = []
    finally:
        conn.close()
    
    return render_template('dashboard/index.html',
                         stats=stats,
                         recent_orders=recent_orders,
                         chart_data=chart_data,
                         status_data=status_data,
                         activity_logs=activity_logs,
                         staff_activity=staff_activity)
