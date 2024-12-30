from flask_mysqldb import MySQL
import bcrypt
from dotenv import load_dotenv
import os
import MySQLdb

# Load environment variables
load_dotenv()

# Connect to MySQL
db = MySQLdb.connect(
    host=os.getenv('MYSQL_HOST'),
    user=os.getenv('MYSQL_USER'),
    passwd=os.getenv('MYSQL_PASSWORD'),
    db=os.getenv('MYSQL_DB')
)

cursor = db.cursor()

# Delete existing admin user if exists
cursor.execute('DELETE FROM users WHERE username = %s', ('admin',))

# Create new admin user
username = 'admin'
password = 'admin123'
email = 'admin@elibrary.com'

# Hash the password
salt = bcrypt.gensalt()
password_bytes = password.encode('utf-8')
hashed_password = bcrypt.hashpw(password_bytes, salt)

print(f"Generated hash: {hashed_password}")

try:
    # Insert new admin user
    cursor.execute(
        'INSERT INTO users (username, email, password, is_admin) VALUES (%s, %s, %s, %s)',
        (username, email, hashed_password, True)
    )
    db.commit()
    print("Admin user created successfully!")
    print("Username: admin")
    print("Password: admin123")
except Exception as e:
    print(f"Error creating admin: {str(e)}")
    db.rollback()
finally:
    cursor.close()
    db.close()
