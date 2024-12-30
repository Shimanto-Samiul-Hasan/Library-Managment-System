### Ultimate Tech Stack
- **Front-End:**
  - **HTML/CSS:** For the basic structure and styling of web pages.
  - **JavaScript (Optional):** For adding interactivity if needed.
  - **Bootstrap (or TailwindCSS):** For responsive and modern UI components.
  - **Jinja (Flask's templating engine):** For dynamic content rendering on the server-side.

- **Back-End:**
  - **Python:** Main programming language for back-end logic.
  - **Flask:** Lightweight web framework for handling requests, routing, and templates.
  - **Flask-MySQLdb:** For connecting to a MySQL database from Flask.
  - **Flask-Session:** To manage sessions for user login/authentication.
  - **bcrypt:** For securely hashing and checking passwords.

- **Database:**
  - **MySQL:** To store user data, books, transactions, etc.

- **API:**
  - **Google Books API:** For fetching book information based on search queries.

---

### Step-by-Step Instructions

#### **Step 1: Project Setup and Initial Configuration**
1. **Create Virtual Environment**
   - Set up a virtual environment to manage dependencies:
     ```bash
     python3 -m venv venv
     source venv/bin/activate  # On Windows: venv\Scripts\activate
     ```

2. **Install Dependencies**
   - Install Flask, Flask-MySQLdb, requests, and bcrypt:
     ```bash
     pip install Flask flask-mysqldb requests bcrypt
     ```

3. **Create Project Structure**
   - Organize the project into files and directories:
     ```plaintext
     /library-system
     ├── /app
     ├── /templates
     ├── /static
     ├── config.py
     ├── requirements.txt
     └── run.py
     ```

4. **Database Setup (MySQL)**
   - Set up the database schema in MySQL:
     ```sql
     CREATE DATABASE library_system;
     
     CREATE TABLE users (
         id INT AUTO_INCREMENT PRIMARY KEY,
         username VARCHAR(100) NOT NULL,
         email VARCHAR(100) NOT NULL,
         password VARCHAR(255) NOT NULL,
         role VARCHAR(20) DEFAULT 'user'
     );
     
     CREATE TABLE books (
         id INT AUTO_INCREMENT PRIMARY KEY,
         title VARCHAR(255),
         author VARCHAR(255),
         description TEXT,
         google_id VARCHAR(255) UNIQUE
     );
     
     CREATE TABLE transactions (
         id INT AUTO_INCREMENT PRIMARY KEY,
         user_id INT,
         book_id INT,
         action ENUM('borrow', 'buy', 'return'),
         date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         FOREIGN KEY (user_id) REFERENCES users(id),
         FOREIGN KEY (book_id) REFERENCES books(id)
     );
     
     CREATE TABLE custom_books (
         id INT AUTO_INCREMENT PRIMARY KEY,
         title VARCHAR(255),
         author VARCHAR(255),
         description TEXT,
         added_by INT,
         FOREIGN KEY (added_by) REFERENCES users(id)
     );
     ```

---

#### **Step 2: Basic Flask Setup**
1. **Initialize Flask App**
   - In `app/__init__.py`, set up the Flask app and database connection:
     ```python
     from flask import Flask
     from flask_mysqldb import MySQL

     app = Flask(__name__)
     app.config['MYSQL_HOST'] = 'localhost'
     app.config['MYSQL_USER'] = 'your_user'
     app.config['MYSQL_PASSWORD'] = 'your_password'
     app.config['MYSQL_DB'] = 'library_system'
     mysql = MySQL(app)

     from app import routes
     ```

2. **Google Books API Integration**
   - Create a function in `app/utils.py` to fetch books from Google Books API:
     ```python
     import requests

     def get_books_from_google(query):
         url = f'https://www.googleapis.com/books/v1/volumes?q={query}'
         response = requests.get(url)
         if response.status_code == 200:
             return response.json()['items']
         return []
     ```

---

#### **Step 3: User Authentication (Login/Registration)**
1. **User Registration**
   - Create a route `/register` in `app/routes.py`:
     ```python
     from flask import render_template, request, redirect, url_for
     from app import mysql
     from werkzeug.security import generate_password_hash

     @app.route('/register', methods=['GET', 'POST'])
     def register():
         if request.method == 'POST':
             username = request.form['username']
             email = request.form['email']
             password = request.form['password']
             hashed_pw = generate_password_hash(password)
             cur = mysql.connection.cursor()
             cur.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)", 
                         (username, email, hashed_pw))
             mysql.connection.commit()
             return redirect(url_for('login'))
         return render_template('register.html')
     ```

2. **User Login**
   - Create a route `/login` in `app/routes.py`:
     ```python
     from flask import session, redirect, request, url_for
     from werkzeug.security import check_password_hash

     @app.route('/login', methods=['GET', 'POST'])
     def login():
         if request.method == 'POST':
             username = request.form['username']
             password = request.form['password']
             cur = mysql.connection.cursor()
             cur.execute("SELECT * FROM users WHERE username = %s", [username])
             user = cur.fetchone()
             if user and check_password_hash(user['password'], password):
                 session['user_id'] = user['id']
                 session['username'] = user['username']
                 return redirect(url_for('dashboard'))
             return 'Invalid username or password'
         return render_template('login.html')
     ```

---

#### **Step 4: Book Management**
1. **Display Books**
   - Create a route `/books` to fetch and display books (Google API + Custom):
     ```python
     @app.route('/books')
     def books():
         query = request.args.get('q', '')
         google_books = get_books_from_google(query)
         cur = mysql.connection.cursor()
         cur.execute("SELECT * FROM custom_books")
         custom_books = cur.fetchall()
         return render_template('books.html', google_books=google_books, custom_books=custom_books)
     ```

2. **Borrow/Return/Buy Books**
   - Create routes `/borrow`, `/return`, and `/buy` to manage transactions:
     ```python
     @app.route('/borrow/<int:book_id>')
     def borrow(book_id):
         user_id = session['user_id']
         cur = mysql.connection.cursor()
         cur.execute("INSERT INTO transactions (user_id, book_id, action) VALUES (%s, %s, 'borrow')", 
                     (user_id, book_id))
         mysql.connection.commit()
         return redirect(url_for('books'))
     ```

---

#### **Step 5: Admin Features**
1. **Admin Authentication and Access**
   - Use user roles to restrict admin access.
   - In `login()` route, check user role before granting admin access.

2. **Add Custom Books**
   - Create an `/admin/add_book` route for the admin to add books manually.

---

#### **Step 6: User Interface**
1. **Create Templates**
   - Use Jinja to create HTML templates (e.g., `login.html`, `dashboard.html`, `books.html`).

2. **Styling with Bootstrap**
   - Integrate Bootstrap to make your templates responsive and stylish.

---

#### **Step 7: Testing and Deployment**
1. **Test Locally**
   - Run the Flask app locally:
     ```bash
     flask run
     ```

2. **Deploy to Heroku**
   - Set up a **Procfile** for deployment:
     ```
     web: python run.py
     ```
   - Push to Heroku and set up the database there.

