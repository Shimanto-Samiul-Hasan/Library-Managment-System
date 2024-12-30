import mysql.connector
from mysql.connector import Error
import requests
import os
from dotenv import load_dotenv
import time
import random

# Load environment variables
load_dotenv()

# Category mappings
CATEGORY_SUBJECTS = {
    'Arts': ['art', 'music', 'photography', 'design', 'architecture'],
    'Business': ['business', 'economics', 'finance', 'management', 'marketing'],
    'Fiction': ['fiction', 'novels', 'fantasy', 'science fiction', 'mystery'],
    'History': ['history', 'world history', 'ancient history', 'military history'],
    'Non-Fiction': ['biography', 'autobiography', 'essays', 'journalism'],
    'Science': ['science', 'physics', 'biology', 'chemistry', 'astronomy'],
    'Self-Help': ['self-help', 'psychology', 'personal development', 'motivation'],
    'Technology': ['technology', 'computers', 'programming', 'engineering']
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DB', 'elibrary')
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

def get_open_library_books(subject, limit=5):
    books = []
    try:
        url = f"http://openlibrary.org/subjects/{subject}.json?limit={limit}"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for work in data.get('works', []):
                cover_id = work.get('cover_id')
                cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
                
                book = {
                    'title': work.get('title'),
                    'authors': ', '.join([author.get('name', '') for author in work.get('authors', [])]),
                    'description': work.get('description', ''),
                    'cover_image': cover_url,
                    'price': round(random.uniform(9.99, 49.99), 2)  # Random price
                }
                books.append(book)
        time.sleep(1)  # Rate limiting
    except Exception as e:
        print(f"Error fetching from OpenLibrary: {e}")
    return books

def get_gutenberg_books(subject, limit=5):
    books = []
    try:
        url = f"https://gutendex.com/books/?topic={subject}&languages=en"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            for result in data.get('results', [])[:limit]:
                book = {
                    'title': result.get('title'),
                    'authors': ', '.join([author.get('name') for author in result.get('authors', [])]),
                    'description': f"A classic book from Project Gutenberg. {result.get('title')} by {', '.join([author.get('name') for author in result.get('authors', [])])}",
                    'cover_image': None,  # Gutenberg doesn't provide cover images
                    'price': round(random.uniform(9.99, 49.99), 2)  # Random price
                }
                books.append(book)
        time.sleep(1)  # Rate limiting
    except Exception as e:
        print(f"Error fetching from Gutenberg: {e}")
    return books

def insert_book(cursor, book, category_id):
    try:
        sql = '''
            INSERT INTO books (title, authors, description, cover_image, category_id, price)
            VALUES (%s, %s, %s, %s, %s, %s)
        '''
        values = (
            book['title'],
            book['authors'],
            book['description'],
            book['cover_image'],
            category_id,
            book['price']
        )
        cursor.execute(sql, values)
        return True
    except Error as e:
        print(f"Error inserting book: {e}")
        return False

def main():
    connection = get_db_connection()
    if not connection:
        return
    
    cursor = connection.cursor(dictionary=True)
    
    # Get categories
    cursor.execute("SELECT * FROM book_categories")
    categories = cursor.fetchall()
    
    for category in categories:
        print(f"\nPopulating books for category: {category['name']}")
        subjects = CATEGORY_SUBJECTS.get(category['name'], [category['name'].lower()])
        
        for subject in subjects:
            # Get books from OpenLibrary
            open_library_books = get_open_library_books(subject, limit=3)
            for book in open_library_books:
                if insert_book(cursor, book, category['id']):
                    print(f"Added OpenLibrary book: {book['title']}")
            
            # Get books from Gutenberg
            gutenberg_books = get_gutenberg_books(subject, limit=2)
            for book in gutenberg_books:
                if insert_book(cursor, book, category['id']):
                    print(f"Added Gutenberg book: {book['title']}")
    
    connection.commit()
    cursor.close()
    connection.close()
    print("\nBook population completed!")

if __name__ == "__main__":
    main()
