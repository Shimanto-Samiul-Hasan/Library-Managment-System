from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
from dotenv import load_dotenv
import os
import requests
import json
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import re

# Load environment variables
load_dotenv()

app = Flask(__name__)

# MySQL configurations
app.config['MYSQL_HOST'] = os.getenv('MYSQL_HOST')
app.config['MYSQL_USER'] = os.getenv('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.getenv('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.getenv('MYSQL_DB')

# Session configuration
app.secret_key = os.getenv('SECRET_KEY')

# Initialize MySQL
mysql = MySQL(app)

# Upload folder configuration
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('loggedin') or not session.get('is_admin'):
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['jpg', 'jpeg', 'png']

def get_open_library_books():
    try:
        url = "https://openlibrary.org/subjects/fiction.json?limit=4"
        response = requests.get(url)
        data = response.json()
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        books = []
        
        for work in data.get('works', []):
            # Check if book already exists
            cursor.execute('SELECT id FROM books WHERE title = %s AND source = "openlibrary"',
                         (work['title'],))
            existing_book = cursor.fetchone()
            
            if not existing_book:
                # Get cover image if available
                cover_id = work.get('cover_id')
                cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg" if cover_id else None
                
                # Get authors
                authors = ', '.join([author.get('name', 'Unknown') for author in work.get('authors', [])])
                
                # Insert into database
                cursor.execute('''
                    INSERT INTO books (title, authors, description, cover_image, preview_link, source) 
                    VALUES (%s, %s, %s, %s, %s, "openlibrary")
                ''', (
                    work['title'],
                    authors,
                    work.get('description', ''),
                    cover_url,
                    f"https://openlibrary.org{work.get('key')}"
                ))
                mysql.connection.commit()
                book_id = cursor.lastrowid
            else:
                book_id = existing_book['id']
            
            # Get book details
            cursor.execute('SELECT * FROM books WHERE id = %s', (book_id,))
            book = cursor.fetchone()
            books.append(book)
        
        cursor.close()
        return books
    except Exception as e:
        print(f"Error fetching Open Library books: {e}")
        return []

def get_gutenberg_books():
    try:
        url = "https://gutendex.com/books"
        response = requests.get(url)
        data = response.json()
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        books = []
        
        for book in data.get('results', [])[:4]:
            title = book.get('title', '')
            authors = ', '.join([author.get('name', '') for author in book.get('authors', [])])
            description = f"A classic book from Project Gutenberg"
            cover_image = book.get('formats', {}).get('image/jpeg')
            preview_link = book.get('formats', {}).get('text/html')
            
            # Check if book already exists
            cursor.execute('SELECT id FROM books WHERE title = %s AND source = "gutenberg"', (title,))
            existing_book = cursor.fetchone()
            
            if not existing_book:
                cursor.execute('''INSERT INTO books (
                    title, authors, description, cover_image, preview_link, source
                ) VALUES (%s, %s, %s, %s, %s, "gutenberg")''',
                    (
                        title,
                        authors,
                        description,
                        cover_image,
                        preview_link
                    )
                )
                mysql.connection.commit()
                book_id = cursor.lastrowid
            else:
                book_id = existing_book['id']
            
            # Get book details
            cursor.execute('SELECT * FROM books WHERE id = %s', (book_id,))
            book_details = cursor.fetchone()
            books.append(book_details)
        
        cursor.close()
        return books
    except Exception as e:
        print(f"Error fetching Gutenberg books: {e}")
        return []

@app.route('/')
def home():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get all categories
    cursor.execute('SELECT * FROM book_categories ORDER BY name')
    categories = cursor.fetchall()
    
    # Get featured books (latest 4 books)
    cursor.execute('''
        SELECT b.*, c.name as category_name 
        FROM books b 
        LEFT JOIN book_categories c ON b.category_id = c.id
        ORDER BY b.created_at DESC 
        LIMIT 4
    ''')
    featured_books = cursor.fetchall()
    
    cursor.close()
    
    return render_template('dashboard.html', 
                         categories=categories,
                         featured_books=featured_books)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    if not query:
        return redirect(url_for('home'))
    
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Search in local database
        search_term = f"%{query}%"
        cursor.execute('''
            SELECT * FROM books 
            WHERE title LIKE %s 
               OR authors LIKE %s 
               OR description LIKE %s
            LIMIT 20
        ''', (search_term, search_term, search_term))
        local_results = cursor.fetchall()
        
        # Get external results
        external_results = []
        if len(local_results) < 10:
            external_results.extend(get_open_library_books())
            if len(external_results) < 4:
                external_results.extend(get_gutenberg_books())
        
        cursor.close()
        return render_template('search.html', 
                             query=query,
                             local_results=local_results,
                             external_results=external_results)
    except Exception as e:
        print(f"Search error: {e}")
        flash('An error occurred while searching', 'error')
        return redirect(url_for('home'))

@app.route('/book/<int:book_id>')
def view_book(book_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get book details with category name
    cursor.execute('''
        SELECT b.*, c.name as category_name 
        FROM books b 
        LEFT JOIN book_categories c ON b.category_id = c.id 
        WHERE b.id = %s
    ''', (book_id,))
    
    book = cursor.fetchone()
    if not book:
        flash('Book not found!', 'danger')
        return redirect(url_for('books'))
    
    # Set default price if not set
    if 'price' not in book or book['price'] is None:
        book['price'] = 29.99  # Default price
    
    # Get related books (same category)
    cursor.execute('''
        SELECT * FROM books 
        WHERE category_id = %s AND id != %s 
        LIMIT 4
    ''', (book['category_id'], book_id))
    related_books = cursor.fetchall()
    
    cursor.close()
    return render_template('book.html', book=book, related_books=related_books)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'loggedin' in session:
        if session.get('is_admin'):
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s AND password = SHA2(%s, 256)', 
                      (username, password))
        user = cursor.fetchone()
        
        if user:
            session['loggedin'] = True
            session['id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            
            # Update last_login timestamp
            cursor.execute('UPDATE users SET last_login = NOW() WHERE id = %s', (user['id'],))
            mysql.connection.commit()
            
            cursor.close()
            
            if user['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('home'))
        else:
            flash('Incorrect username/password!', 'danger')
            cursor.close()
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if not session.get('loggedin'):
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get borrowed books
    cursor.execute('''
        SELECT b.id, b.title, b.authors, b.cover_image, b.description, b.category_id,
               bb.id as borrow_id, bb.borrow_date, bb.return_date, bb.days_borrowed, 
               bb.total_cost, bb.returned, bb.actual_return_date
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        WHERE bb.user_id = %s
        ORDER BY bb.borrow_date DESC
    ''', (session['id'],))
    borrowed_books = cursor.fetchall()
    
    # Get purchased books
    cursor.execute('''
        SELECT b.id, b.title, b.authors, b.cover_image, b.description, b.category_id,
               pb.id as purchase_id, pb.purchase_date, pb.price as purchased_price
        FROM purchased_books pb
        JOIN books b ON pb.book_id = b.id
        WHERE pb.user_id = %s
        ORDER BY pb.purchase_date DESC
    ''', (session['id'],))
    purchased_books = cursor.fetchall()
    
    cursor.close()
    
    return render_template('dashboard.html',
                         borrowed_books=borrowed_books,
                         purchased_books=purchased_books,
                         now=datetime.now())

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Check if username exists
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        if cursor.fetchone():
            flash('Username already exists!', 'danger')
            return redirect(url_for('register'))
        
        # Insert new user with SHA2 hashed password
        cursor.execute('''
            INSERT INTO users (username, password, email, created_at) 
            VALUES (%s, SHA2(%s, 256), %s, NOW())
        ''', (username, password, email))
        mysql.connection.commit()
        cursor.close()
        
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/books')
def books():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get category filter
    category_id = request.args.get('category', type=int)
    search_query = request.args.get('search', '')
    
    # Base query
    query = '''
        SELECT b.*, c.name as category_name 
        FROM books b 
        LEFT JOIN book_categories c ON b.category_id = c.id
        WHERE 1=1
    '''
    params = []
    
    # Add category filter if specified
    if category_id:
        query += ' AND b.category_id = %s'
        params.append(category_id)
    
    # Add search filter if specified
    if search_query:
        query += ' AND (b.title LIKE %s OR b.authors LIKE %s OR b.description LIKE %s)'
        search_pattern = f'%{search_query}%'
        params.extend([search_pattern] * 3)
    
    query += ' ORDER BY b.created_at DESC'
    
    # Execute the query
    cursor.execute(query, tuple(params))
    books = cursor.fetchall()
    
    # Get all categories for the filter
    cursor.execute('SELECT * FROM book_categories ORDER BY name')
    categories = cursor.fetchall()
    
    cursor.close()
    
    return render_template('books.html', 
                         books=books, 
                         categories=categories,
                         selected_category=category_id,
                         search_query=search_query)

@app.route('/search_books', methods=['GET', 'POST'])
def search_books():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        query = request.form.get('query')
        results = search_google_books(query)
        
        if results and 'items' in results:
            books = [get_book_details(item) for item in results['items']]
            return render_template('search_results.html', books=books)
    
    return render_template('search_books.html')

@app.route('/borrow/<int:book_id>')
def borrow(book_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    success, message = borrow_book(cursor, session['id'], book_id)
    mysql.connection.commit()
    cursor.close()
    
    flash(message)
    return redirect(url_for('books'))

@app.route('/return/<int:book_id>')
def return_book_route(book_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    success, message = return_book(cursor, session['id'], book_id)
    mysql.connection.commit()
    cursor.close()
    
    flash(message)
    return redirect(url_for('dashboard'))

@app.route('/buy/<int:book_id>')
def buy(book_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    success, message = buy_book(cursor, session['id'], book_id)
    mysql.connection.commit()
    cursor.close()
    
    flash(message)
    return redirect(url_for('books'))

@app.route('/borrow/<int:book_id>', methods=['POST'])
def borrow_book_route(book_id):
    if not session.get('loggedin'):
        flash('Please login to borrow books.', 'danger')
        return redirect(url_for('login'))
    
    days = int(request.form.get('days', 1))
    if days < 1 or days > 30:
        flash('Please select between 1 and 30 days.', 'danger')
        return redirect(url_for('view_book', book_id=book_id))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if user has already borrowed this book and not returned
    cursor.execute('''
        SELECT * FROM borrowed_books 
        WHERE user_id = %s AND book_id = %s AND returned = FALSE
    ''', (session['id'], book_id))
    
    if cursor.fetchone():
        flash('You have already borrowed this book.', 'danger')
        return redirect(url_for('view_book', book_id=book_id))
    
    # Calculate cost and return date
    cost_per_day = 2.00
    total_cost = days * cost_per_day
    
    cursor.execute('''
        INSERT INTO borrowed_books 
        (user_id, book_id, days_borrowed, return_date, total_cost)
        VALUES (%s, %s, %s, DATE_ADD(NOW(), INTERVAL %s DAY), %s)
    ''', (session['id'], book_id, days, days, total_cost))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Book borrowed successfully for {days} days. Total cost: ${total_cost:.2f}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/buy/<int:book_id>', methods=['POST'])
def buy_book_route(book_id):
    if not session.get('loggedin'):
        flash('Please login to buy books.', 'danger')
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get book price
    cursor.execute('SELECT price FROM books WHERE id = %s', (book_id,))
    book = cursor.fetchone()
    if not book:
        flash('Book not found.', 'danger')
        return redirect(url_for('home'))
    
    # Check if user has already purchased this book
    cursor.execute('SELECT * FROM purchased_books WHERE user_id = %s AND book_id = %s',
                  (session['id'], book_id))
    if cursor.fetchone():
        flash('You have already purchased this book.', 'info')
        return redirect(url_for('view_book', book_id=book_id))
    
    # Record the purchase
    cursor.execute('''
        INSERT INTO purchased_books (user_id, book_id, price)
        VALUES (%s, %s, %s)
    ''', (session['id'], book_id, book['price']))
    
    mysql.connection.commit()
    cursor.close()
    
    flash(f'Book purchased successfully for ${book["price"]:.2f}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard_route():
    if not session.get('loggedin'):
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get borrowed books
    cursor.execute('''
        SELECT b.id, b.title, b.authors, b.cover_image, b.description, b.category_id,
               bb.id as borrow_id, bb.borrow_date, bb.return_date, bb.days_borrowed, 
               bb.total_cost, bb.returned, bb.actual_return_date
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        WHERE bb.user_id = %s
        ORDER BY bb.borrow_date DESC
    ''', (session['id'],))
    borrowed_books = cursor.fetchall()
    
    # Get purchased books
    cursor.execute('''
        SELECT b.id, b.title, b.authors, b.cover_image, b.description, b.category_id,
               pb.id as purchase_id, pb.purchase_date, pb.price as purchased_price
        FROM purchased_books pb
        JOIN books b ON pb.book_id = b.id
        WHERE pb.user_id = %s
        ORDER BY pb.purchase_date DESC
    ''', (session['id'],))
    purchased_books = cursor.fetchall()
    
    cursor.close()
    
    return render_template('dashboard.html',
                         borrowed_books=borrowed_books,
                         purchased_books=purchased_books)

# Helper function to log admin activities
def log_admin_activity(action_type, target_id, details):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''INSERT INTO admin_logs (admin_id, action_type, target_id, details) 
                   VALUES (%s, %s, %s, %s)''',
                   (session['id'], action_type, target_id, details))
    mysql.connection.commit()
    cursor.close()

@app.route('/admin/books/add', methods=['POST'])
@admin_required
def admin_add_book():
    if 'cover_image' not in request.files:
        flash('No cover image uploaded', 'warning')
        return redirect(url_for('admin_books'))
        
    file = request.files['cover_image']
    if file.filename == '':
        flash('No cover image selected', 'warning')
        return redirect(url_for('admin_books'))
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        cover_path = url_for('static', filename=f'uploads/{filename}')
    else:
        cover_path = None
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''INSERT INTO books (
        title, authors, description, cover_image, source, added_by
    ) VALUES (%s, %s, %s, %s, "admin", %s)''',
        (
            request.form['title'],
            request.form.get('authors', ''),
            request.form['description'],
            cover_path,
            session['id']
        )
    )
    book_id = cursor.lastrowid
    mysql.connection.commit()
    cursor.close()
    
    # Log the activity
    log_admin_activity('ADD_BOOK', book_id, f"Added book: {request.form['title']}")
    
    flash('Book added successfully', 'success')
    return redirect(url_for('admin_books'))

@app.route('/admin/books')
@admin_required
def admin_books():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT b.*, c.name as category_name, u.username as added_by_user
        FROM books b 
        LEFT JOIN book_categories c ON b.category_id = c.id
        LEFT JOIN users u ON b.added_by = u.id
        WHERE b.source = 'admin'
        ORDER BY b.created_at DESC
    ''')
    books = cursor.fetchall()
    
    # Get categories for the add book form
    cursor.execute('SELECT * FROM book_categories ORDER BY name')
    categories = cursor.fetchall()
    
    cursor.close()
    return render_template('admin/books.html', books=books, categories=categories)

@app.route('/admin/books/edit/<int:book_id>', methods=['POST'])
@admin_required
def admin_edit_book(book_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if 'cover_image' in request.files and request.files['cover_image'].filename != '':
        file = request.files['cover_image']
        if allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            cover_path = url_for('static', filename=f'uploads/{filename}')
            cursor.execute('''UPDATE books SET title = %s, description = %s, cover_image = %s 
                         WHERE id = %s''',
                         (request.form['title'], request.form['description'], cover_path, book_id))
    else:
        cursor.execute('''UPDATE books SET title = %s, description = %s WHERE id = %s''',
                     (request.form['title'], request.form['description'], book_id))
    
    mysql.connection.commit()
    cursor.close()
    
    # Log the activity
    log_admin_activity('EDIT_BOOK', book_id, f"Edited book: {request.form['title']}")
    
    flash('Book updated successfully', 'success')
    return redirect(url_for('admin_books'))

@app.route('/admin/books/delete/<int:book_id>')
@admin_required
def admin_delete_book(book_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('DELETE FROM books WHERE id = %s', (book_id,))
    mysql.connection.commit()
    cursor.close()
    
    flash('Book deleted successfully', 'success')
    return redirect(url_for('admin_books'))

@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_add_user():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']
    is_admin = 'is_admin' in request.form
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if username exists
    cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
    if cursor.fetchone():
        flash('Username already exists!', 'danger')
        return redirect(url_for('admin_users'))
    
    # Check if email exists
    cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
    if cursor.fetchone():
        flash('Email already exists!', 'danger')
        return redirect(url_for('admin_users'))
    
    # Insert new user with hashed password
    cursor.execute('''
        INSERT INTO users (username, email, password, is_admin)
        VALUES (%s, %s, SHA2(%s, 256), %s)
    ''', (username, email, password, is_admin))
    mysql.connection.commit()
    cursor.close()
    
    flash('User added successfully!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/make-admin/<int:user_id>')
@admin_required
def admin_make_admin(user_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get username before updating
    cursor.execute('SELECT username FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    username = user['username'] if user else 'Unknown user'
    
    cursor.execute('UPDATE users SET is_admin = 1 WHERE id = %s', (user_id,))
    mysql.connection.commit()
    cursor.close()
    
    # Log the activity
    log_admin_activity('MAKE_ADMIN', user_id, f"Promoted user to admin: {username}")
    
    flash('User promoted to admin successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if user is admin
    cursor.execute('SELECT is_admin FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    if user and user['is_admin']:
        flash('Cannot delete admin user!', 'danger')
        return redirect(url_for('admin_users'))
    
    # Delete user
    cursor.execute('DELETE FROM users WHERE id = %s', (user_id,))
    mysql.connection.commit()
    cursor.close()
    
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/edit_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_edit_user(user_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get current user data
    cursor.execute('SELECT username FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    old_username = user['username'] if user else 'Unknown user'
    
    # Update user data
    cursor.execute('''UPDATE users SET username = %s, email = %s WHERE id = %s''',
                 (request.form['username'], request.form['email'], user_id))
    
    # If password is provided, update it
    if request.form.get('password'):
        hashed_password = generate_password_hash(request.form['password'])
        cursor.execute('UPDATE users SET password = %s WHERE id = %s',
                     (hashed_password, user_id))
    
    mysql.connection.commit()
    cursor.close()
    
    # Log the activity
    log_admin_activity('EDIT_USER', user_id, 
                      f"Edited user: {old_username} -> {request.form['username']}")
    
    flash('User updated successfully', 'success')
    return redirect(url_for('admin_users'))

@app.route('/admin/toggle_user_status/<int:user_id>')
@admin_required
def admin_toggle_user_status(user_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get current user status
    cursor.execute('SELECT username, is_active FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    
    if user:
        new_status = not user['is_active']
        cursor.execute('UPDATE users SET is_active = %s WHERE id = %s',
                     (new_status, user_id))
        mysql.connection.commit()
        
        # Log the activity
        status_text = "activated" if new_status else "deactivated"
        log_admin_activity('TOGGLE_USER_STATUS', user_id,
                         f"{status_text.capitalize()} user: {user['username']}")
        
        flash(f'User {status_text} successfully', 'success')
    else:
        flash('User not found', 'error')
    
    cursor.close()
    return redirect(url_for('admin_users'))

@app.route('/admin/books/categories', methods=['GET', 'POST'])
@admin_required
def admin_book_categories():
    if request.method == 'POST':
        category_name = request.form.get('category_name')
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        if request.form.get('action') == 'add':
            cursor.execute('INSERT INTO book_categories (name) VALUES (%s)',
                         (category_name,))
            category_id = cursor.lastrowid
            mysql.connection.commit()
            
            # Log the activity
            log_admin_activity('ADD_CATEGORY', category_id,
                             f"Added book category: {category_name}")
            
            flash('Category added successfully', 'success')
            
        elif request.form.get('action') == 'delete':
            category_id = request.form.get('category_id')
            cursor.execute('DELETE FROM book_categories WHERE id = %s',
                         (category_id,))
            mysql.connection.commit()
            
            # Log the activity
            log_admin_activity('DELETE_CATEGORY', category_id,
                             f"Deleted book category: {category_name}")
            
            flash('Category deleted successfully', 'success')
        
        cursor.close()
        return redirect(url_for('admin_book_categories'))
    
    # Get all categories
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM book_categories ORDER BY name')
    categories = cursor.fetchall()
    cursor.close()
    
    return render_template('admin/book_categories.html', categories=categories)

@app.route('/admin/users')
@admin_required
def admin_users():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
    users = cursor.fetchall()
    cursor.close()
    return render_template('admin/users.html', users=users)

@app.route('/admin')
@admin_required
def admin_dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get total books
    cursor.execute('SELECT COUNT(*) as count FROM books WHERE source = "admin"')
    total_books = cursor.fetchone()['count']
    
    # Get total users
    cursor.execute('SELECT COUNT(*) as count FROM users')
    total_users = cursor.fetchone()['count']
    
    # Get active users in last 24 hours
    cursor.execute('SELECT COUNT(*) as count FROM users WHERE last_login > DATE_SUB(NOW(), INTERVAL 24 HOUR)')
    active_users = cursor.fetchone()['count']
    
    # Get recent users
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 5')
    recent_users = cursor.fetchall()
    
    # Get admin logs
    cursor.execute('SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT 10')
    admin_logs = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin/dashboard.html',
                         total_books=total_books,
                         total_users=total_users,
                         active_users=active_users,
                         recent_users=recent_users,
                         admin_logs=admin_logs)

@app.route('/admin/users/<int:user_id>')
@admin_required
def get_user(user_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()
    cursor.close()
    if user:
        return jsonify({
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'is_admin': user['is_admin']
        })
    return jsonify({'error': 'User not found'}), 404

@app.route('/my-books')
def my_books():
    if not session.get('loggedin'):
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Get borrowed books
        cursor.execute('''
            SELECT 
                b.id,
                b.title,
                b.authors,
                b.cover_image,
                bb.borrow_date,
                bb.due_date,
                bb.return_date,
                DATEDIFF(COALESCE(bb.return_date, NOW()), bb.borrow_date) as days_borrowed,
                CASE 
                    WHEN bb.return_date IS NULL AND NOW() > bb.due_date THEN 'Overdue'
                    WHEN bb.return_date IS NOT NULL THEN 'Returned'
                    ELSE 'Active'
                END as status
            FROM borrowed_books bb
            JOIN books b ON b.id = bb.book_id
            WHERE bb.user_id = %s
            ORDER BY bb.borrow_date DESC
        ''', (session['id'],))
        borrowed_books = cursor.fetchall()

        # Get purchased books
        cursor.execute('''
            SELECT 
                b.id,
                b.title,
                b.authors,
                b.cover_image,
                pb.purchase_date,
                pb.price
            FROM purchased_books pb
            JOIN books b ON b.id = pb.book_id
            WHERE pb.user_id = %s
            ORDER BY pb.purchase_date DESC
        ''', (session['id'],))
        purchased_books = cursor.fetchall()

        return render_template('my_books.html', 
                             borrowed_books=borrowed_books,
                             purchased_books=purchased_books)
    except Exception as e:
        print(str(e))
        flash('An error occurred while fetching your books.', 'danger')
        return redirect(url_for('index'))
    finally:
        cursor.close()

@app.route('/admin/borrowed-books')
@admin_required
def admin_borrowed_books():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('''
        SELECT bb.*, b.title as book_title, b.authors, b.cover_image,
               u.username, u.email
        FROM borrowed_books bb
        JOIN books b ON bb.book_id = b.id
        JOIN users u ON bb.user_id = u.id
        ORDER BY bb.borrow_date DESC
    ''')
    borrowed_books = cursor.fetchall()
    
    cursor.close()
    return render_template('admin/borrowed_books.html', borrowed_books=borrowed_books, now=datetime.now())

@app.route('/admin/purchased-books')
@admin_required
def admin_purchased_books():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('''
        SELECT pb.*, b.title as book_title, b.authors, b.cover_image,
               u.username, u.email
        FROM purchased_books pb
        JOIN books b ON pb.book_id = b.id
        JOIN users u ON pb.user_id = u.id
        ORDER BY pb.purchase_date DESC
    ''')
    purchased_books = cursor.fetchall()
    
    cursor.close()
    return render_template('admin/purchased_books.html', purchased_books=purchased_books)

@app.route('/return-book/<int:borrow_id>', methods=['POST'])
def return_book(borrow_id):
    if not session.get('loggedin'):
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Get borrow details
        cursor.execute('''
            SELECT bb.*, b.title as book_title 
            FROM borrowed_books bb
            JOIN books b ON bb.book_id = b.id
            WHERE bb.id = %s AND (bb.user_id = %s OR %s)
        ''', (borrow_id, session['id'], session.get('is_admin', False)))
        
        borrow = cursor.fetchone()
        if not borrow:
            flash('Borrow record not found!', 'danger')
            return redirect(url_for('my_books'))
        
        if borrow['returned']:
            flash('Book has already been returned!', 'warning')
        else:
            now = datetime.now()
            return_date = borrow['return_date']
            
            # Calculate refund if returning early
            if now < return_date:
                days_remaining = (return_date - now).days
                if days_remaining > 0:
                    refund_amount = days_remaining * 2.00  # $2 per day
                    
                    # Record the refund
                    cursor.execute('''
                        INSERT INTO refunds (borrow_id, amount, reason)
                        VALUES (%s, %s, %s)
                    ''', (
                        borrow_id, 
                        refund_amount,
                        f'Early return refund for {days_remaining} days'
                    ))
                    
                    # Update the total cost in borrowed_books
                    cursor.execute('''
                        UPDATE borrowed_books 
                        SET total_cost = total_cost - %s
                        WHERE id = %s
                    ''', (refund_amount, borrow_id))
                    
                    flash(f'Refund of ${refund_amount:.2f} processed for early return!', 'success')
            
            # Mark as returned
            cursor.execute('''
                UPDATE borrowed_books 
                SET returned = TRUE, actual_return_date = NOW()
                WHERE id = %s
            ''', (borrow_id,))
            
            mysql.connection.commit()
            flash(f'Book "{borrow["book_title"]}" returned successfully!', 'success')
    
    except Exception as e:
        mysql.connection.rollback()
        flash(f'Error processing return: {str(e)}', 'danger')
    finally:
        cursor.close()
    
    if session.get('is_admin'):
        return redirect(url_for('admin_borrowed_books'))
    return redirect(url_for('my_books'))

@app.route('/add_to_cart/<int:book_id>', methods=['POST'])
def add_to_cart(book_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if book exists
    cursor.execute('SELECT * FROM books WHERE id = %s', (book_id,))
    book = cursor.fetchone()
    if not book:
        flash('Book not found!', 'danger')
        return redirect(url_for('books'))
    
    # Check if book is already in cart
    cursor.execute('SELECT * FROM cart_items WHERE user_id = %s AND book_id = %s',
                  (session['id'], book_id))
    cart_item = cursor.fetchone()
    
    if cart_item:
        # Update quantity
        cursor.execute('''
            UPDATE cart_items 
            SET quantity = quantity + 1 
            WHERE user_id = %s AND book_id = %s
        ''', (session['id'], book_id))
    else:
        # Add new item to cart
        cursor.execute('''
            INSERT INTO cart_items (user_id, book_id, quantity)
            VALUES (%s, %s, 1)
        ''', (session['id'], book_id))
    
    mysql.connection.commit()
    flash('Book added to cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get cart items with book details
    cursor.execute('''
        SELECT ci.*, b.title, b.authors, b.cover_image, b.price
        FROM cart_items ci
        JOIN books b ON ci.book_id = b.id
        WHERE ci.user_id = %s
    ''', (session['id'],))
    cart_items = cursor.fetchall()
    
    # Calculate total
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    
    cursor.close()
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal)

@app.route('/remove_from_cart/<int:item_id>', methods=['POST'])
def remove_from_cart(item_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('DELETE FROM cart_items WHERE id = %s AND user_id = %s',
                  (item_id, session['id']))
    mysql.connection.commit()
    cursor.close()
    
    flash('Item removed from cart!', 'success')
    return redirect(url_for('cart'))

@app.route('/update_cart/<int:item_id>', methods=['POST'])
def update_cart(item_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    quantity = int(request.form.get('quantity', 1))
    if quantity < 1:
        quantity = 1
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        UPDATE cart_items 
        SET quantity = %s 
        WHERE id = %s AND user_id = %s
    ''', (quantity, item_id, session['id']))
    mysql.connection.commit()
    cursor.close()
    
    return redirect(url_for('cart'))

@app.route('/checkout')
def checkout():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get cart items
    cursor.execute('''
        SELECT ci.*, b.title, b.authors, b.price
        FROM cart_items ci
        JOIN books b ON ci.book_id = b.id
        WHERE ci.user_id = %s
    ''', (session['id'],))
    cart_items = cursor.fetchall()
    
    if not cart_items:
        return redirect(url_for('cart'))
    
    # Calculate totals
    subtotal = sum(item['price'] * item['quantity'] for item in cart_items)
    total = subtotal  # Add tax or shipping if needed
    
    cursor.close()
    return render_template('checkout.html',
                         cart_items=cart_items,
                         subtotal=subtotal,
                         total=total)

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    payment_method = request.form.get('payment_method')
    if not payment_method:
        flash('Please select a payment method!', 'danger')
        return redirect(url_for('checkout'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Get cart items
        cursor.execute('''
            SELECT ci.*, b.price, b.id as book_id, b.title
            FROM cart_items ci
            JOIN books b ON b.id = ci.book_id
            WHERE ci.user_id = %s
        ''', (session['id'],))
        cart_items = cursor.fetchall()
        
        if not cart_items:
            flash('Your cart is empty!', 'warning')
            return redirect(url_for('cart'))
        
        # Calculate total
        total_amount = sum(item['price'] * item['quantity'] for item in cart_items)
        
        # Process payment
        if payment_method == 'card':
            card_number = request.form.get('card_number')
            if not card_number:
                flash('Please enter a card number!', 'danger')
                return redirect(url_for('checkout'))
            payment_details = card_number
            
        elif payment_method == 'alipay':
            phone = request.form.get('alipay_phone')
            if not phone:
                flash('Please enter your phone number!', 'danger')
                return redirect(url_for('checkout'))
            payment_details = phone
            
        elif payment_method == 'wepay':
            phone = request.form.get('wepay_phone')
            if not phone:
                flash('Please enter your phone number!', 'danger')
                return redirect(url_for('checkout'))
            payment_details = phone
            
        # Create order
        cursor.execute('''
            INSERT INTO orders (user_id, total_amount, payment_method, payment_details)
            VALUES (%s, %s, %s, %s)
        ''', (session['id'], total_amount, payment_method, payment_details))
        order_id = cursor.lastrowid
        
        # Add order items
        for item in cart_items:
            cursor.execute('''
                INSERT INTO order_items (order_id, book_id, quantity, price)
                VALUES (%s, %s, %s, %s)
            ''', (order_id, item['book_id'], item['quantity'], item['price']))
            
            # Add to purchased books
            cursor.execute('''
                INSERT INTO purchased_books (user_id, book_id, purchase_date, price)
                VALUES (%s, %s, NOW(), %s)
            ''', (session['id'], item['book_id'], item['price']))
        
        # Clear cart
        cursor.execute('DELETE FROM cart_items WHERE user_id = %s', (session['id'],))
        mysql.connection.commit()
        
        # Success message
        if payment_method == 'card':
            flash('Payment successful! Your books have been added to your library.', 'success')
        else:
            flash(f'Payment successful! Your books have been added to your library.', 'success')
        
        return redirect(url_for('my_books'))
        
    except Exception as e:
        print(str(e))  # For debugging
        mysql.connection.rollback()
        flash('Payment failed! Please try again.', 'danger')
        return redirect(url_for('checkout'))
    
    finally:
        cursor.close()

@app.route('/direct_checkout/<int:book_id>/<action>', methods=['POST'])
def direct_checkout(book_id, action):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    if action not in ['buy', 'borrow']:
        flash('Invalid action!', 'danger')
        return redirect(url_for('book', book_id=book_id))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Get book details
        cursor.execute('SELECT * FROM books WHERE id = %s', (book_id,))
        book = cursor.fetchone()
        
        if not book:
            flash('Book not found!', 'danger')
            return redirect(url_for('books'))
        
        if action == 'buy':
            # Store book in session for checkout
            session['direct_purchase'] = {
                'book_id': book_id,
                'quantity': 1,
                'price': float(book['price']),
                'title': book['title']
            }
            return redirect(url_for('direct_payment'))
        else:  # borrow
            # Check if user has already borrowed this book
            cursor.execute('''
                SELECT * FROM borrowed_books 
                WHERE user_id = %s AND book_id = %s AND return_date IS NULL
            ''', (session['id'], book_id))
            if cursor.fetchone():
                flash('You have already borrowed this book.', 'warning')
                return redirect(url_for('book', book_id=book_id))
            
            # Store book in session for checkout
            session['direct_borrow'] = {
                'book_id': book_id,
                'title': book['title']
            }
            return redirect(url_for('direct_payment'))
            
    except Exception as e:
        flash('An error occurred! Please try again.', 'danger')
        return redirect(url_for('book', book_id=book_id))
    finally:
        cursor.close()

@app.route('/direct_payment')
def direct_payment():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    # Check if we have a direct purchase or borrow in session
    direct_purchase = session.get('direct_purchase')
    direct_borrow = session.get('direct_borrow')
    
    if not direct_purchase and not direct_borrow:
        return redirect(url_for('books'))
    
    if direct_purchase:
        total = direct_purchase['price']
        items = [direct_purchase]
        is_purchase = True
    else:
        total = 2.00  # Borrowing fee is $2
        items = [direct_borrow]
        is_purchase = False
    
    return render_template('checkout.html', 
                         cart_items=items, 
                         total=total,
                         is_direct=True,
                         is_purchase=is_purchase)

@app.route('/process_direct_payment', methods=['POST'])
def process_direct_payment():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    # Check if we have a direct purchase or borrow in session
    direct_purchase = session.get('direct_purchase')
    direct_borrow = session.get('direct_borrow')
    
    if not direct_purchase and not direct_borrow:
        return redirect(url_for('books'))
    
    payment_method = request.form.get('payment_method')
    if not payment_method:
        flash('Please select a payment method!', 'danger')
        return redirect(url_for('direct_payment'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    try:
        # Process payment details
        if payment_method == 'card':
            card_number = request.form.get('card_number')
            if not card_number:
                flash('Please enter a card number!', 'danger')
                return redirect(url_for('direct_payment'))
            payment_details = card_number
        elif payment_method == 'alipay':
            phone = request.form.get('alipay_phone')
            if not phone:
                flash('Please enter your phone number!', 'danger')
                return redirect(url_for('direct_payment'))
            payment_details = phone
        elif payment_method == 'wepay':
            phone = request.form.get('wepay_phone')
            if not phone:
                flash('Please enter your phone number!', 'danger')
                return redirect(url_for('direct_payment'))
            payment_details = phone
        else:
            flash('Invalid payment method!', 'danger')
            return redirect(url_for('direct_payment'))

        if direct_purchase:
            # Create order for purchase
            cursor.execute('''
                INSERT INTO orders (user_id, total_amount, payment_method, payment_details, order_type)
                VALUES (%s, %s, %s, %s, 'purchase')
            ''', (session['id'], direct_purchase['price'], payment_method, payment_details))
            mysql.connection.commit()
            order_id = cursor.lastrowid
            
            # Add order item
            cursor.execute('''
                INSERT INTO order_items (order_id, book_id, quantity, price)
                VALUES (%s, %s, %s, %s)
            ''', (order_id, direct_purchase['book_id'], 1, direct_purchase['price']))
            mysql.connection.commit()
            
            # Add to purchased books
            cursor.execute('''
                INSERT INTO purchased_books (user_id, book_id, price)
                VALUES (%s, %s, %s)
            ''', (session['id'], direct_purchase['book_id'], direct_purchase['price']))
            mysql.connection.commit()
            
            flash('Payment successful! Your book has been added to your library.', 'success')
            
        else:  # direct_borrow
            # Get selected days
            days = int(request.form.get('days', 14))
            
            # Create order for borrowing fee
            cursor.execute('''
                INSERT INTO orders (user_id, total_amount, payment_method, payment_details, order_type)
                VALUES (%s, %s, %s, %s, 'borrow')
            ''', (session['id'], 2.00, payment_method, payment_details))
            mysql.connection.commit()
            order_id = cursor.lastrowid
            
            # Add to borrowed books
            cursor.execute('''
                INSERT INTO borrowed_books (user_id, book_id, borrow_date, due_date, order_id)
                VALUES (%s, %s, NOW(), DATE_ADD(NOW(), INTERVAL %s DAY), %s)
            ''', (session['id'], direct_borrow['book_id'], days, order_id))
            mysql.connection.commit()
            
            flash(f'Payment successful! Book borrowed. Please return it within {days} days.', 'success')
        
        # Clear session
        if 'direct_purchase' in session:
            session.pop('direct_purchase')
        if 'direct_borrow' in session:
            session.pop('direct_borrow')
        
        return redirect(url_for('my_books'))
        
    except Exception as e:
        print(f"Payment Error: {str(e)}")  # For debugging
        mysql.connection.rollback()
        flash('Transaction failed! Please try again.', 'danger')
        return redirect(url_for('direct_payment'))
    
    finally:
        cursor.close()

@app.route('/admin/transactions')
def admin_transactions():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    try:
        # Get all transactions with user and book details
        cursor.execute('''
            SELECT 
                o.*,
                u.username,
                CASE 
                    WHEN o.order_type = 'purchase' THEN
                        (SELECT b.title 
                         FROM order_items oi 
                         JOIN books b ON b.id = oi.book_id 
                         WHERE oi.order_id = o.id 
                         LIMIT 1)
                    ELSE
                        (SELECT b.title 
                         FROM borrowed_books bb 
                         JOIN books b ON b.id = bb.book_id 
                         WHERE bb.order_id = o.id)
                END as book_title
            FROM orders o
            JOIN users u ON u.id = o.user_id
            ORDER BY o.order_date DESC
        ''')
        transactions = cursor.fetchall()
        return render_template('admin/transactions.html', transactions=transactions)
    except Exception as e:
        print(str(e))  # For debugging
        flash('An error occurred while fetching transactions.', 'danger')
        return redirect(url_for('admin_dashboard'))
    finally:
        cursor.close()

if __name__ == '__main__':
    app.run(debug=True)
