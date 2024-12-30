import os
import requests
from datetime import datetime, timedelta
from flask import current_app

def search_google_books(query, max_results=10):
    """Search books using Google Books API"""
    api_key = os.getenv('GOOGLE_BOOKS_API_KEY')
    base_url = "https://www.googleapis.com/books/v1/volumes"
    
    params = {
        'q': query,
        'maxResults': max_results,
        'key': api_key
    }
    
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching books: {e}")
        return None

def get_book_details(book_data):
    """Extract relevant book details from Google Books API response"""
    volume_info = book_data.get('volumeInfo', {})
    
    return {
        'title': volume_info.get('title', 'Unknown Title'),
        'author': ', '.join(volume_info.get('authors', ['Unknown Author'])),
        'isbn': volume_info.get('industryIdentifiers', [{}])[0].get('identifier', ''),
        'description': volume_info.get('description', ''),
        'category': ', '.join(volume_info.get('categories', ['Uncategorized'])),
        'thumbnail': volume_info.get('imageLinks', {}).get('thumbnail', '')
    }

def add_book_to_db(cursor, book_details, quantity=1, price=9.99):
    """Add a book to the database"""
    query = """
    INSERT INTO books (title, author, isbn, description, category, quantity, price)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        book_details['title'],
        book_details['author'],
        book_details['isbn'],
        book_details['description'],
        book_details['category'],
        quantity,
        price
    )
    
    cursor.execute(query, values)
    return cursor.lastrowid

def get_available_books(cursor):
    """Get all available books from the database"""
    query = """
    SELECT id, title, author, isbn, description, category, quantity, price 
    FROM books 
    WHERE quantity > 0
    """
    cursor.execute(query)
    return cursor.fetchall()

def borrow_book(cursor, user_id, book_id):
    """Borrow a book"""
    # Check if book is available
    cursor.execute("SELECT quantity FROM books WHERE id = %s", (book_id,))
    book = cursor.fetchone()
    
    if not book or book[0] <= 0:
        return False, "Book not available"
    
    # Check if user already has this book borrowed
    cursor.execute("""
        SELECT id FROM transactions 
        WHERE user_id = %s AND book_id = %s 
        AND transaction_type = 'borrow' 
        AND status = 'active'
    """, (user_id, book_id))
    
    if cursor.fetchone():
        return False, "You already have this book borrowed"
    
    # Create transaction and update book quantity
    return_date = datetime.now() + timedelta(days=14)
    cursor.execute("""
        INSERT INTO transactions (user_id, book_id, transaction_type, return_date)
        VALUES (%s, %s, 'borrow', %s)
    """, (user_id, book_id, return_date))
    
    cursor.execute("""
        UPDATE books SET quantity = quantity - 1
        WHERE id = %s
    """, (book_id,))
    
    return True, "Book borrowed successfully"

def return_book(cursor, user_id, book_id):
    """Return a borrowed book"""
    cursor.execute("""
        SELECT id FROM transactions 
        WHERE user_id = %s AND book_id = %s 
        AND transaction_type = 'borrow' 
        AND status = 'active'
    """, (user_id, book_id))
    
    transaction = cursor.fetchone()
    if not transaction:
        return False, "No active borrow record found"
    
    # Update transaction and book quantity
    cursor.execute("""
        UPDATE transactions 
        SET status = 'completed' 
        WHERE id = %s
    """, (transaction[0],))
    
    cursor.execute("""
        UPDATE books 
        SET quantity = quantity + 1
        WHERE id = %s
    """, (book_id,))
    
    return True, "Book returned successfully"

def buy_book(cursor, user_id, book_id):
    """Buy a book"""
    cursor.execute("SELECT quantity, price FROM books WHERE id = %s", (book_id,))
    book = cursor.fetchone()
    
    if not book or book[0] <= 0:
        return False, "Book not available"
    
    # Create transaction and update book quantity
    cursor.execute("""
        INSERT INTO transactions (user_id, book_id, transaction_type)
        VALUES (%s, %s, 'buy')
    """, (user_id, book_id))
    
    cursor.execute("""
        UPDATE books SET quantity = quantity - 1
        WHERE id = %s
    """, (book_id,))
    
    return True, f"Book purchased successfully for ${book[1]}"
