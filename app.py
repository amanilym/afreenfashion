# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import random
import string
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from functools import wraps
import os
from datetime import datetime
from config import Config
from database import init_db

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = 'static/images/products'

# Database helper functions
def get_db_connection():
    conn = sqlite3.connect('afreen_fashion.db')
    conn.row_factory = sqlite3.Row
    return conn


def convert_sqlite_date(date_str):
    if isinstance(date_str, str):
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            try:
                return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return date_str
    return date_str

# Email configuration
def send_email(to_email, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = Config.MAIL_USERNAME
    msg['To'] = to_email
    
    try:
        with smtplib.SMTP_SSL(Config.MAIL_SERVER, Config.MAIL_PORT) as server:
            server.login(Config.MAIL_USERNAME, Config.MAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

# Authentication decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'danger')
            return redirect(url_for('login'))
        
        conn = get_db_connection()
        user = conn.execute('SELECT is_admin FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        
        if not user or not user['is_admin']:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    conn = get_db_connection()
    latest_products = conn.execute('''
        SELECT p.*, GROUP_CONCAT(ps.size) as available_sizes 
        FROM products p
        LEFT JOIN product_sizes ps ON p.id = ps.product_id
        WHERE p.is_active = 1
        GROUP BY p.id
        ORDER BY p.created_at DESC
        LIMIT 8
    ''').fetchall()
    conn.close()
    return render_template('index.html', products=latest_products)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            session['is_admin'] = user['is_admin']
            flash('Login successful!', 'success')
            
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))
        else:
            flash('Invalid email or password.', 'danger')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password)
        
        try:
            conn = get_db_connection()
            conn.execute(
                'INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                (name, email, hashed_password)
            )
            conn.commit()
            conn.close()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.', 'danger')
            conn.close()
    
    return render_template('signup.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        
        conn = get_db_connection()
        user = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        
        if user:
            # Generate OTP
            otp = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.now() + timedelta(minutes=15)
            
            # Delete any existing tokens
            conn.execute('DELETE FROM reset_tokens WHERE user_id = ?', (user['id'],))
            
            # Store new token
            conn.execute(
                'INSERT INTO reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)',
                (user['id'], otp, expires_at)
            )
            conn.commit()
            conn.close()
            
            # Send email
            subject = "Afreen Fashion - Password Reset OTP"
            body = f"Your OTP for password reset is: {otp}\n\nThis OTP is valid for 15 minutes."
            
            if send_email(email, subject, body):
                session['reset_email'] = email
                flash('OTP has been sent to your email.', 'success')
                return redirect(url_for('reset_password'))
            else:
                flash('Failed to send OTP. Please try again.', 'danger')
        else:
            conn.close()
            flash('Email not found.', 'danger')
    
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if 'reset_email' not in session:
        return redirect(url_for('forgot_password'))
    
    if request.method == 'POST':
        otp = request.form['otp']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('reset_password'))
        
        conn = get_db_connection()
        user = conn.execute('SELECT id FROM users WHERE email = ?', (session['reset_email'],)).fetchone()
        
        if user:
            token = conn.execute(
                'SELECT * FROM reset_tokens WHERE user_id = ? AND token = ? AND expires_at > ?',
                (user['id'], otp, datetime.now())
            ).fetchone()
            
            if token:
                hashed_password = generate_password_hash(new_password)
                conn.execute(
                    'UPDATE users SET password = ? WHERE id = ?',
                    (hashed_password, user['id'])
                )
                conn.execute('DELETE FROM reset_tokens WHERE user_id = ?', (user['id'],))
                conn.commit()
                conn.close()
                
                session.pop('reset_email', None)
                flash('Password reset successfully. Please login with your new password.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Invalid or expired OTP.', 'danger')
        else:
            conn.close()
            flash('User not found.', 'danger')
    
    return render_template('reset_password.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/products')
def products():
    search = request.args.get('search', '')
    conn = get_db_connection()
    
    query = '''
        SELECT p.*, GROUP_CONCAT(ps.size) as available_sizes 
        FROM products p
        LEFT JOIN product_sizes ps ON p.id = ps.product_id
        WHERE p.is_active = 1
    '''
    
    params = []
    
    if search:
        query += ' AND (p.name LIKE ? OR p.design_number LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    query += ' GROUP BY p.id ORDER BY p.created_at DESC'
    products = conn.execute(query, params).fetchall()
    conn.close()
    
    return render_template('products.html', products=products, search=search)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    product = conn.execute('''
        SELECT p.*, GROUP_CONCAT(ps.size) as available_sizes 
        FROM products p
        LEFT JOIN product_sizes ps ON p.id = ps.product_id
        WHERE p.id = ? AND p.is_active = 1
        GROUP BY p.id
    ''', (product_id,)).fetchone()
    
    if not product:
        conn.close()
        flash('Product not found.', 'danger')
        return redirect(url_for('products'))
    
    # Get available sizes with quantities
    sizes = conn.execute('''
        SELECT size, quantity FROM product_sizes 
        WHERE product_id = ? AND quantity > 0
        ORDER BY 
            CASE size 
                WHEN 'M' THEN 1
                WHEN 'L' THEN 2
                WHEN 'XL' THEN 3
                WHEN '2XL' THEN 4
                ELSE 5
            END
    ''', (product_id,)).fetchall()
    
    conn.close()
    return render_template('product_detail.html', product=product, sizes=sizes)

@app.route('/add-to-cart', methods=['POST'])
@login_required
def add_to_cart():
    product_id = request.form['product_id']
    size = request.form['size']
    quantity = int(request.form['quantity'])
    
    conn = get_db_connection()
    
    # Check product availability
    available = conn.execute('''
        SELECT quantity FROM product_sizes 
        WHERE product_id = ? AND size = ?
    ''', (product_id, size)).fetchone()
    
    if not available or available['quantity'] < quantity:
        conn.close()
        flash('Selected size/quantity not available.', 'danger')
        return redirect(url_for('product_detail', product_id=product_id))
    
    # Get or create cart for user
    cart = conn.execute('''
        SELECT id FROM carts WHERE user_id = ? LIMIT 1
    ''', (session['user_id'],)).fetchone()
    
    if not cart:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO carts (user_id) VALUES (?)', (session['user_id'],))
        cart_id = cursor.lastrowid
    else:
        cart_id = cart['id']
    
    # Check if item already in cart
    cart_item = conn.execute('''
        SELECT id, quantity FROM cart_items 
        WHERE cart_id = ? AND product_id = ? AND size = ?
    ''', (cart_id, product_id, size)).fetchone()
    
    if cart_item:
        new_quantity = cart_item['quantity'] + quantity
        conn.execute('''
            UPDATE cart_items SET quantity = ? 
            WHERE id = ?
        ''', (new_quantity, cart_item['id']))
    else:
        conn.execute('''
            INSERT INTO cart_items (cart_id, product_id, size, quantity)
            VALUES (?, ?, ?, ?)
        ''', (cart_id, product_id, size, quantity))
    
    conn.commit()
    conn.close()
    
    flash('Item added to cart!', 'success')
    return redirect(url_for('product_detail', product_id=product_id))

@app.route('/cart')
@login_required
def view_cart():
    conn = get_db_connection()
    
    cart_items = conn.execute('''
        SELECT ci.id, ci.quantity, ci.size, p.id as product_id, p.name, p.design_number, p.price, p.image_path
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        JOIN carts c ON ci.cart_id = c.id
        WHERE c.user_id = ?
    ''', (session['user_id'],)).fetchall()
    
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    conn.close()
    
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/update-cart', methods=['POST'])
@login_required
def update_cart():
    cart_item_id = request.form['cart_item_id']
    new_quantity = int(request.form['quantity'])
    
    conn = get_db_connection()
    
    # Get current cart item details
    cart_item = conn.execute('''
        SELECT ci.*, ps.quantity as available_quantity
        FROM cart_items ci
        JOIN product_sizes ps ON ci.product_id = ps.product_id AND ci.size = ps.size
        WHERE ci.id = ?
    ''', (cart_item_id,)).fetchone()
    
    if not cart_item:
        conn.close()
        flash('Cart item not found.', 'danger')
        return redirect(url_for('view_cart'))
    
    if new_quantity <= 0:
        conn.execute('DELETE FROM cart_items WHERE id = ?', (cart_item_id,))
    else:
        if new_quantity > cart_item['available_quantity']:
            conn.close()
            flash('Not enough stock available.', 'danger')
            return redirect(url_for('view_cart'))
        
        conn.execute('''
            UPDATE cart_items SET quantity = ? WHERE id = ?
        ''', (new_quantity, cart_item_id))
    
    conn.commit()
    conn.close()
    flash('Cart updated successfully!', 'success')
    return redirect(url_for('view_cart'))

@app.route('/remove-from-cart/<int:cart_item_id>')
@login_required
def remove_from_cart(cart_item_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM cart_items WHERE id = ?', (cart_item_id,))
    conn.commit()
    conn.close()
    
    flash('Item removed from cart.', 'success')
    return redirect(url_for('view_cart'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    conn = get_db_connection()
    
    # Get cart items
    cart_items = conn.execute('''
        SELECT ci.quantity, ci.size, p.id as product_id, p.name, p.design_number, p.price
        FROM cart_items ci
        JOIN products p ON ci.product_id = p.id
        JOIN carts c ON ci.cart_id = c.id
        WHERE c.user_id = ?
    ''', (session['user_id'],)).fetchall()
    
    if not cart_items:
        conn.close()
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('view_cart'))
    
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    
    if request.method == 'POST':
        shipping_address = request.form['shipping_address']
        
        # Create order
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO orders (user_id, total_amount, shipping_address)
            VALUES (?, ?, ?)
        ''', (session['user_id'], total, shipping_address))
        order_id = cursor.lastrowid
        
        # Add order items
        for item in cart_items:
            cursor.execute('''
                INSERT INTO order_items (order_id, product_id, size, quantity, price)
                VALUES (?, ?, ?, ?, ?)
            ''', (order_id, item['product_id'], item['size'], item['quantity'], item['price']))
            
            # Update inventory
            cursor.execute('''
                UPDATE product_sizes 
                SET quantity = quantity - ?
                WHERE product_id = ? AND size = ?
            ''', (item['quantity'], item['product_id'], item['size']))
        
        # Clear cart
        cart = conn.execute('SELECT id FROM carts WHERE user_id = ?', (session['user_id'],)).fetchone()
        if cart:
            conn.execute('DELETE FROM cart_items WHERE cart_id = ?', (cart['id'],))
        
        conn.commit()
        conn.close()
        
        flash('Order placed successfully!', 'success')
        return redirect(url_for('order_confirmation', order_id=order_id))
    
    conn.close()
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/order-confirmation/<int:order_id>')
@login_required
def order_confirmation(order_id):
    conn = get_db_connection()
    
    order_data = conn.execute('''
        SELECT o.*, oi.quantity, oi.size, oi.price, p.name, p.design_number
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE o.id = ? AND o.user_id = ?
    ''', (order_id, session['user_id'])).fetchall()
    
    if not order_data:
        conn.close()
        flash('Order not found.', 'danger')
        return redirect(url_for('index'))
    
    # Convert to dictionary format
    order_details = {
        'id': order_data[0]['id'],
        'order_date': order_data[0]['order_date'],
        'total_amount': order_data[0]['total_amount'],
        'status': order_data[0]['status'],
        'shipping_address': order_data[0]['shipping_address'],
        'items': []
    }
    
    # Convert date string to datetime if needed
    if isinstance(order_details['order_date'], str):
        try:
            order_details['order_date'] = datetime.strptime(
                order_details['order_date'], '%Y-%m-%d %H:%M:%S.%f')
        except ValueError:
            order_details['order_date'] = datetime.strptime(
                order_details['order_date'], '%Y-%m-%d %H:%M:%S')
    
    for item in order_data:
        order_details['items'].append({
            'name': item['name'],
            'design_number': item['design_number'],
            'size': item['size'],
            'quantity': item['quantity'],
            'price': item['price']
        })
    
    conn.close()
    return render_template('order_confirmation.html', order=order_details)

@app.route('/my-orders')
@login_required
def my_orders():
    conn = get_db_connection()
    
    orders_data = conn.execute('''
        SELECT o.id, o.order_date, o.total_amount, o.status, 
               GROUP_CONCAT(p.name || ' (' || oi.size || ', Qty: ' || oi.quantity || ')', ', ') as items
        FROM orders o
        JOIN order_items oi ON o.id = oi.order_id
        JOIN products p ON oi.product_id = p.id
        WHERE o.user_id = ?
        GROUP BY o.id
        ORDER BY o.order_date DESC
    ''', (session['user_id'],)).fetchall()
    
    # Convert order_date strings to datetime objects
    orders = []
    for order in orders_data:
        order_dict = dict(order)
        if isinstance(order_dict['order_date'], str):
            order_dict['order_date'] = datetime.strptime(order_dict['order_date'], '%Y-%m-%d %H:%M:%S')
        orders.append(order_dict)
    order_dict['order_date'] = convert_sqlite_date(order_dict['order_date'])
    conn.close()
    return render_template('orders.html', orders=orders)

# Admin routes
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    conn = get_db_connection()
    
    # Get counts for dashboard
    product_count = conn.execute('SELECT COUNT(*) as count FROM products').fetchone()['count']
    order_count = conn.execute('SELECT COUNT(*) as count FROM orders').fetchone()['count']
    pending_orders = conn.execute('SELECT COUNT(*) as count FROM orders WHERE status = "Pending"').fetchone()['count']
    
    # Recent orders - convert string dates to datetime objects
    recent_orders = []
    orders_data = conn.execute('''
        SELECT o.id, o.order_date, o.total_amount, o.status, u.name as customer_name
        FROM orders o
        JOIN users u ON o.user_id = u.id
        ORDER BY o.order_date DESC
        LIMIT 5
    ''').fetchall()
    
    for order in orders_data:
        order_dict = dict(order)
        # Convert string to datetime if it's not already
        if isinstance(order_dict['order_date'], str):
            order_dict['order_date'] = datetime.strptime(order_dict['order_date'], '%Y-%m-%d %H:%M:%S')
        recent_orders.append(order_dict)
    
    conn.close()
    return render_template('admin/dashboard.html', 
                         product_count=product_count,
                         order_count=order_count,
                         pending_orders=pending_orders,
                         recent_orders=recent_orders)

@app.route('/admin/products')
@admin_required
def admin_products():
    search = request.args.get('search', '')
    conn = get_db_connection()
    
    query = 'SELECT * FROM products WHERE 1=1'
    params = []
    
    if search:
        query += ' AND (name LIKE ? OR design_number LIKE ?)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    query += ' ORDER BY created_at DESC'
    products = conn.execute(query, params).fetchall()
    
    # Convert Row objects to dictionaries and add sizes
    products_list = []
    for product in products:
        product_dict = dict(product)
        sizes = conn.execute('''
            SELECT size, quantity FROM product_sizes WHERE product_id = ?
        ''', (product['id'],)).fetchall()
        product_dict['sizes'] = sizes
        products_list.append(product_dict)
    
    conn.close()
    return render_template('admin/inventory.html', products=products_list, search=search)

@app.route('/admin/products/add', methods=['GET', 'POST'])
@admin_required
def add_product():
    if request.method == 'POST':
        design_number = request.form['design_number']
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        
        # Handle image upload
        image = request.files['image']
        image_path = None
        
        if image and allowed_file(image.filename):
            filename = f"product_{design_number}.{image.filename.rsplit('.', 1)[1].lower()}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            image_path = f"images/products/{filename}"
        
        conn = get_db_connection()
        
        try:
            # Add product
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO products (design_number, name, description, price, image_path)
                VALUES (?, ?, ?, ?, ?)
            ''', (design_number, name, description, price, image_path))
            product_id = cursor.lastrowid
            
            # Add sizes and quantities
            sizes = ['M', 'L', 'XL', '2XL']
            for size in sizes:
                quantity = int(request.form.get(f'quantity_{size.lower()}', 0))
                if quantity > 0:
                    cursor.execute('''
                        INSERT INTO product_sizes (product_id, size, quantity)
                        VALUES (?, ?, ?)
                    ''', (product_id, size, quantity))
            
            conn.commit()
            conn.close()
            
            flash('Product added successfully!', 'success')
            return redirect(url_for('admin_products'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('Design number already exists.', 'danger')
    
    return render_template('admin/add_product.html')

@app.route('/admin/products/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    conn = get_db_connection()
    
    if request.method == 'POST':
        design_number = request.form['design_number']
        name = request.form['name']
        description = request.form['description']
        price = float(request.form['price'])
        is_active = 'is_active' in request.form
        
        # Handle image upload
        image = request.files['image']
        image_path = None
        
        if image and allowed_file(image.filename):
            # Delete old image if exists
            old_image = conn.execute('SELECT image_path FROM products WHERE id = ?', (product_id,)).fetchone()
            if old_image and old_image['image_path']:
                try:
                    os.remove(os.path.join('static', old_image['image_path']))
                except OSError:
                    pass
            
            # Save new image
            filename = f"product_{design_number}.{image.filename.rsplit('.', 1)[1].lower()}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image.save(image_path)
            image_path = f"images/products/{filename}"
        
        try:
            # Update product
            if image_path:
                conn.execute('''
                    UPDATE products 
                    SET design_number = ?, name = ?, description = ?, price = ?, image_path = ?, is_active = ?
                    WHERE id = ?
                ''', (design_number, name, description, price, image_path, is_active, product_id))
            else:
                conn.execute('''
                    UPDATE products 
                    SET design_number = ?, name = ?, description = ?, price = ?, is_active = ?
                    WHERE id = ?
                ''', (design_number, name, description, price, is_active, product_id))
            
            # Update sizes and quantities
            sizes = ['M', 'L', 'XL', '2XL']
            for size in sizes:
                quantity = int(request.form.get(f'quantity_{size.lower()}', 0))
                
                # Check if size exists
                existing = conn.execute('''
                    SELECT id FROM product_sizes WHERE product_id = ? AND size = ?
                ''', (product_id, size)).fetchone()
                
                if existing:
                    if quantity > 0:
                        conn.execute('''
                            UPDATE product_sizes SET quantity = ? 
                            WHERE id = ?
                        ''', (quantity, existing['id']))
                    else:
                        conn.execute('DELETE FROM product_sizes WHERE id = ?', (existing['id'],))
                elif quantity > 0:
                    conn.execute('''
                        INSERT INTO product_sizes (product_id, size, quantity)
                        VALUES (?, ?, ?)
                    ''', (product_id, size, quantity))
            
            conn.commit()
            conn.close()
            
            flash('Product updated successfully!', 'success')
            return redirect(url_for('admin_products'))
        except sqlite3.IntegrityError:
            conn.close()
            flash('Design number already exists.', 'danger')
            return redirect(url_for('edit_product', product_id=product_id))
    
    # GET request
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if not product:
        conn.close()
        flash('Product not found.', 'danger')
        return redirect(url_for('admin_products'))
    
    sizes = conn.execute('''
        SELECT size, quantity FROM product_sizes WHERE product_id = ?
    ''', (product_id,)).fetchall()
    
    size_quantities = {size['size']: size['quantity'] for size in sizes}
    conn.close()
    
    return render_template('admin/edit_product.html', product=product, size_quantities=size_quantities)

@app.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    conn = get_db_connection()
    
    # Get image path to delete file
    product = conn.execute('SELECT image_path FROM products WHERE id = ?', (product_id,)).fetchone()
    
    if product and product['image_path']:
        try:
            os.remove(os.path.join('static', product['image_path']))
        except OSError:
            pass
    
    # Delete product
    conn.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()
    
    flash('Product deleted successfully!', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status = request.args.get('status', 'all')
    conn = get_db_connection()
    
    query = '''
        SELECT o.*, u.name as customer_name
        FROM orders o
        JOIN users u ON o.user_id = u.id
    '''
    
    params = []
    
    if status != 'all':
        query += ' WHERE o.status = ?'
        params.append(status)
    
    query += ' ORDER BY o.order_date DESC'
    orders_data = conn.execute(query, params).fetchall()
    
    # Convert order_date strings to datetime objects
    orders = []
    for order in orders_data:
        order_dict = dict(order)
        if isinstance(order_dict['order_date'], str):
            try:
                # Try parsing with microseconds
                order_dict['order_date'] = datetime.strptime(order_dict['order_date'], '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                # Fallback to format without microseconds
                order_dict['order_date'] = datetime.strptime(order_dict['order_date'], '%Y-%m-%d %H:%M:%S')
        orders.append(order_dict)
    
    conn.close()
    return render_template('admin/orders.html', orders=orders, status_filter=status)

@app.route('/admin/orders/<int:order_id>')
@admin_required
def admin_order_detail(order_id):
    conn = get_db_connection()
    
    order = conn.execute('''
        SELECT o.*, u.name as customer_name, u.email as customer_email
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.id = ?
    ''', (order_id,)).fetchone()
    
    if not order:
        conn.close()
        flash('Order not found.', 'danger')
        return redirect(url_for('admin_orders'))
    
    items = conn.execute('''
        SELECT oi.*, p.name, p.design_number, p.image_path
        FROM order_items oi
        JOIN products p ON oi.product_id = p.id
        WHERE oi.order_id = ?
    ''', (order_id,)).fetchall()
    
    conn.close()
    
    # Convert to dictionary and process date
    order_dict = dict(order)
    order_dict['order_date'] = convert_sqlite_date(order_dict['order_date'])
    
    return render_template('admin/order_detail.html', order=order_dict, items=items)

@app.route('/admin/orders/update-status/<int:order_id>', methods=['POST'])
@admin_required
def update_order_status(order_id):
    new_status = request.form['status']
    
    conn = get_db_connection()
    conn.execute('''
        UPDATE orders SET status = ? WHERE id = ?
    ''', (new_status, order_id))
    conn.commit()
    conn.close()
    
    flash('Order status updated successfully!', 'success')
    return redirect(url_for('admin_order_detail', order_id=order_id))

# Helper functions
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg', 'gif'}

if __name__ == '__main__':
    init_db()
    app.run(debug=True)