"""Orders routes"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from models.database import get_db, login_required, admin_required, log_activity
from services.order_service import generate_order_id, generate_barcode, calculate_price
from services.pdf_service import generate_invoice_pdf
import json
from datetime import datetime, date

orders_bp = Blueprint('orders', __name__)


@orders_bp.route('/')
@login_required
def index():
    conn = get_db()
    try:
        status_filter = request.args.get('status', 'all')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 15
        offset = (page - 1) * per_page
        
        with conn.cursor() as cursor:
            base_query = """
                SELECT o.*, c.name as customer_name, c.phone 
                FROM orders o 
                JOIN customers c ON o.customer_id = c.id
                WHERE 1=1
            """
            params = []
            
            if status_filter != 'all':
                base_query += " AND o.status = %s"
                params.append(status_filter)
            
            if search:
                base_query += " AND (c.name LIKE %s OR c.phone LIKE %s OR o.order_id LIKE %s)"
                params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
            
            # Count total
            cursor.execute(f"SELECT COUNT(*) as cnt FROM ({base_query}) sub", params)
            total = cursor.fetchone()['cnt']
            
            base_query += " ORDER BY o.created_at DESC LIMIT %s OFFSET %s"
            params.extend([per_page, offset])
            cursor.execute(base_query, params)
            orders = cursor.fetchall()
            
        total_pages = (total + per_page - 1) // per_page
        
    except Exception as e:
        print(f"Orders error: {e}")
        orders = []
        total = 0
        total_pages = 1
    finally:
        conn.close()
    
    return render_template('orders/index.html',
                         orders=orders,
                         status_filter=status_filter,
                         search=search,
                         page=page,
                         total_pages=total_pages,
                         total=total)


@orders_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_order():
    conn = get_db()
    
    if request.method == 'POST':
        try:
            # Customer info
            customer_name = request.form.get('customer_name', '').strip()
            customer_phone = request.form.get('customer_phone', '').strip()
            customer_email = request.form.get('customer_email', '').strip()
            
            # Order info
            service_type = request.form.get('service_type')
            dress_quantity = int(request.form.get('dress_quantity', 1))
            delivery_date = request.form.get('delivery_date')
            priority = request.form.get('priority', 'normal')
            notes = request.form.get('notes', '')
            payment_method = request.form.get('payment_method', 'cash')
            gst_enabled = request.form.get('gst_enabled') == 'on'
            
            # Items JSON from form
            items_json = request.form.get('items_data', '[]')
            items = json.loads(items_json)
            
            if not all([customer_name, customer_phone, service_type, delivery_date]):
                flash('Please fill all required fields.', 'danger')
                return redirect(url_for('orders.new_order'))
            
            # Get or create customer
            with conn.cursor() as cursor:
                cursor.execute("SELECT id FROM customers WHERE phone = %s", (customer_phone,))
                customer = cursor.fetchone()
                
                if not customer:
                    cursor.execute(
                        """INSERT INTO customers (name, phone, email) VALUES (%s, %s, %s)""",
                        (customer_name, customer_phone, customer_email)
                    )
                    customer_id = cursor.lastrowid
                else:
                    customer_id = customer['id']
                
                # Calculate totals
                total_amount = sum(item.get('total_price', 0) for item in items)
                if not items:
                    total_amount = calculate_price(service_type, dress_quantity)
                
                gst_amount = round(total_amount * 0.18, 2) if gst_enabled else 0
                final_amount = total_amount + gst_amount
                
                # Generate unique IDs
                order_id = generate_order_id()
                barcode = generate_barcode(order_id)
                
                # Create order
                cursor.execute("""
                    INSERT INTO orders 
                    (order_id, customer_id, created_by, service_type, dress_quantity, 
                     total_amount, gst_amount, final_amount, delivery_date, priority, notes, barcode)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (order_id, customer_id, session['user_id'], service_type, dress_quantity,
                      total_amount, gst_amount, final_amount, delivery_date, priority, notes, barcode))
                
                db_order_id = cursor.lastrowid
                
                # Insert order items
                for item in items:
                    cursor.execute("""
                        INSERT INTO order_items (order_id, item_name, item_type, service_type, quantity, unit_price, total_price)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (db_order_id, item.get('item_name', ''), item.get('item_type', ''),
                          item.get('service_type', service_type), item.get('quantity', 1),
                          item.get('unit_price', 0), item.get('total_price', 0)))
                
                # Create payment record
                cursor.execute("""
                    INSERT INTO payments (order_id, amount, payment_method, payment_status)
                    VALUES (%s, %s, %s, 'pending')
                """, (db_order_id, final_amount, payment_method))
                
                # Update customer stats
                cursor.execute("""
                    UPDATE customers SET total_visits = total_visits + 1 WHERE id = %s
                """, (customer_id,))
                
            conn.commit()
            
            log_activity(session['user_id'], 'CREATE_ORDER', 'orders', 
                        f"Created order {order_id}", request.remote_addr)
            
            flash(f'Order {order_id} created successfully!', 'success')
            return redirect(url_for('orders.view_order', order_id=order_id))
            
        except Exception as e:
            conn.rollback()
            flash(f'Error creating order: {str(e)}', 'danger')
            print(f"Order creation error: {e}")
        finally:
            conn.close()
    
    # GET - Load pricing data
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM service_pricing WHERE is_active = TRUE ORDER BY item_type, service_type")
            pricing = cursor.fetchall()
    except:
        pricing = []
    finally:
        conn.close()
    
    return render_template('orders/new_order.html', pricing=pricing)


@orders_bp.route('/view/<order_id>')
@login_required
def view_order(order_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, c.name as customer_name, c.phone, c.email, c.address,
                       u.full_name as staff_name
                FROM orders o 
                JOIN customers c ON o.customer_id = c.id
                JOIN users u ON o.created_by = u.id
                WHERE o.order_id = %s
            """, (order_id,))
            order = cursor.fetchone()
            
            if not order:
                flash('Order not found.', 'danger')
                return redirect(url_for('orders.index'))
            
            cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order['id'],))
            items = cursor.fetchall()
            
            cursor.execute("SELECT * FROM payments WHERE order_id = %s", (order['id'],))
            payment = cursor.fetchone()
            
    except Exception as e:
        print(f"View order error: {e}")
        flash('Error loading order.', 'danger')
        return redirect(url_for('orders.index'))
    finally:
        conn.close()
    
    return render_template('orders/view_order.html', order=order, items=items, payment=payment)


@orders_bp.route('/update-status/<order_id>', methods=['POST'])
@login_required
def update_status(order_id):
    new_status = request.form.get('status')
    valid_statuses = ['pending', 'processing', 'ready', 'delivered', 'cancelled']
    
    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('orders.view_order', order_id=order_id))
    
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE orders SET status = %s WHERE order_id = %s",
                (new_status, order_id)
            )
            
            # If delivered, update payment and customer total
            if new_status == 'delivered':
                cursor.execute("""
                    UPDATE payments p 
                    JOIN orders o ON p.order_id = o.id
                    SET p.payment_status = 'paid', p.paid_at = NOW()
                    WHERE o.order_id = %s AND p.payment_status = 'pending'
                """, (order_id,))
                
                cursor.execute("""
                    UPDATE customers c
                    JOIN orders o ON o.customer_id = c.id
                    SET c.total_spent = c.total_spent + o.final_amount
                    WHERE o.order_id = %s AND o.status = 'delivered'
                """, (order_id,))
        
        conn.commit()
        log_activity(session['user_id'], 'UPDATE_STATUS', 'orders',
                    f"Order {order_id} status -> {new_status}", request.remote_addr)
        flash(f'Order status updated to {new_status}.', 'success')
    except Exception as e:
        conn.rollback()
        flash('Error updating status.', 'danger')
        print(f"Status update error: {e}")
    finally:
        conn.close()
    
    return redirect(url_for('orders.view_order', order_id=order_id))


@orders_bp.route('/download-pdf/<order_id>')
@login_required
def download_pdf(order_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT o.*, c.name as customer_name, c.phone, c.email, c.address,
                       u.full_name as staff_name
                FROM orders o 
                JOIN customers c ON o.customer_id = c.id
                JOIN users u ON o.created_by = u.id
                WHERE o.order_id = %s
            """, (order_id,))
            order = cursor.fetchone()
            
            cursor.execute("SELECT * FROM order_items WHERE order_id = %s", (order['id'],))
            items = cursor.fetchall()
            
            cursor.execute("SELECT * FROM payments WHERE order_id = %s", (order['id'],))
            payment = cursor.fetchone()
        
        pdf_path = generate_invoice_pdf(order, items, payment)
        
        with conn.cursor() as cursor:
            cursor.execute("UPDATE orders SET pdf_path = %s WHERE order_id = %s", (pdf_path, order_id))
        conn.commit()
        
    except Exception as e:
        flash(f'Error generating PDF: {e}', 'danger')
        print(f"PDF error: {e}")
        return redirect(url_for('orders.view_order', order_id=order_id))
    finally:
        conn.close()
    
    return send_file(pdf_path, as_attachment=True, download_name=f'Invoice_{order_id}.pdf')


@orders_bp.route('/delete/<order_id>', methods=['POST'])
@admin_required
def delete_order(order_id):
    conn = get_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))
        conn.commit()
        log_activity(session['user_id'], 'DELETE_ORDER', 'orders',
                    f"Deleted order {order_id}", request.remote_addr)
        flash('Order deleted.', 'success')
    except Exception as e:
        conn.rollback()
        flash('Error deleting order.', 'danger')
    finally:
        conn.close()
    return redirect(url_for('orders.index'))
