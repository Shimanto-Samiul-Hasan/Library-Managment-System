import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def setup_database():
    try:
        # Connect to MySQL server
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', '')
        )
        
        if connection.is_connected():
            cursor = connection.cursor()
            
            # Drop and recreate tables
            cursor.execute("DROP DATABASE IF EXISTS elibrary")
            print("Dropped existing database")

            # Create database
            cursor.execute("CREATE DATABASE elibrary")
            print("Created new database")

            # Select database
            cursor.execute("USE elibrary")
            print("Selected database")

            # Read and execute schema.sql
            with open('schema.sql', 'r') as file:
                sql_commands = file.read().split(';')
                
                for command in sql_commands:
                    if command.strip():
                        cursor.execute(command + ';')
                        connection.commit()
                        print(f"Executed: {command[:50]}...")
            
            print("Database setup completed successfully!")
            
            # Close connection
            cursor.close()
            connection.close()
            print("MySQL connection is closed")
            
    except Error as e:
        print(f"Error while connecting to MySQL: {e}")

if __name__ == "__main__":
    setup_database()
