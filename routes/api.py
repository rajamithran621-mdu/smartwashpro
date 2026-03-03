"""API routes"""
from flask import Blueprint, request, jsonify, session
from models.database import get_db, login_required
from services.order_service import calculate_price

api_bp = Blueprint('api', __name__)


def api_login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


@api_bp.route('/scan-barcode', methods=['POST'])
@api_login_required
def scan_barcode():
    barcode = request.json.get('barcode', '').strip()
    if not barcode:
        return jsonify({'error': 'No barcode provided'}), 400
    
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, c.name as customer_name, c.phone
                FROM orders o JOIN customers c ON o.customer_id = c.id
                WHERE o.barcode = %s OR o.order_id = %s
            """, (barcode, barcode))
            order = cursor.fetchone()
        
        if order:
            # Convert datetime objects to strings
            for key, val in order.items():
                if hasattr(val, 'isoformat'):
                    order[key] = val.isoformat()
            return jsonify({'success': True, 'order': order})
        else:
            return jsonify({'success': False, 'message': 'Order not found'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/calculate-price', methods=['POST'])
@api_login_required
def api_calculate_price():
    data = request.json
    service_type = data.get('service_type', 'wash')
    quantity = int(data.get('quantity', 1))
    
    price = calculate_price(service_type, quantity)
    return jsonify({'price': price})


@api_bp.route('/pricing', methods=['GET'])
@api_login_required
def get_pricing():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM service_pricing WHERE is_active = TRUE ORDER BY item_type")
            pricing = cursor.fetchall()
        return jsonify({'pricing': pricing})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/dashboard-stats', methods=['GET'])
@api_login_required
def dashboard_stats():
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COALESCE(SUM(CASE WHEN DATE(paid_at)=CURDATE() AND payment_status='paid' THEN amount ELSE 0 END), 0) as today_revenue,
                    COALESCE(SUM(CASE WHEN MONTH(paid_at)=MONTH(CURDATE()) AND YEAR(paid_at)=YEAR(CURDATE()) AND payment_status='paid' THEN amount ELSE 0 END), 0) as monthly_revenue
                FROM payments
            """)
            revenue = cursor.fetchone()
            
            cursor.execute("""
                SELECT status, COUNT(*) as count FROM orders GROUP BY status
            """)
            statuses = cursor.fetchall()
        
        return jsonify({'revenue': revenue, 'statuses': statuses})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/search-customer', methods=['GET'])
@api_login_required
def search_customer():
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({'customer': None})
    
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM customers WHERE phone = %s", (phone,))
            customer = cursor.fetchone()
        return jsonify({'customer': customer})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


@api_bp.route('/send-whatsapp/<order_id>', methods=['POST'])
@api_login_required
def send_whatsapp(order_id):
    """WhatsApp notification via WhatsApp Business API"""
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, c.name as customer_name, c.phone
                FROM orders o JOIN customers c ON o.customer_id = c.id
                WHERE o.order_id = %s
            """, (order_id,))
            order = cursor.fetchone()
        
        if not order:
            return jsonify({'error': 'Order not found'}), 404
        
        # Format WhatsApp message
        message_type = request.json.get('type', 'confirmation')
        phone = order['phone'].replace('+', '').replace(' ', '').replace('-', '')
        if not phone.startswith('91'):
            phone = '91' + phone
        
        if message_type == 'confirmation':
            message = f"🧺 *SmartWash Pro*\n\nDear {order['customer_name']},\n\nYour order has been confirmed!\n\n📋 Order ID: *{order['order_id']}*\n👕 Items: {order['dress_quantity']} piece(s)\n🔧 Service: {order['service_type'].replace('_', ' ').title()}\n💰 Amount: ₹{order['final_amount']}\n📅 Delivery: {order['delivery_date']}\n\nThank you for choosing SmartWash Pro! 🌟"
        elif message_type == 'ready':
            message = f"✅ *SmartWash Pro*\n\nDear {order['customer_name']},\n\nYour order is *READY* for pickup!\n\n📋 Order ID: *{order['order_id']}*\n💰 Amount: ₹{order['final_amount']}\n\nPlease visit our store to collect your garments. 🏪"
        else:
            message = f"🧾 *SmartWash Pro*\n\nDear {order['customer_name']},\n\nYour invoice for Order {order['order_id']} is ready.\nAmount: ₹{order['final_amount']}\n\nThank you! 🙏"
        
        whatsapp_url = f"https://api.whatsapp.com/send?phone={phone}&text={message}"
        
        with conn.cursor() as cursor:
            cursor.execute("UPDATE orders SET whatsapp_sent = TRUE WHERE order_id = %s", (order_id,))
        conn.commit()
        
        return jsonify({'success': True, 'whatsapp_url': whatsapp_url, 'message': message})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()
