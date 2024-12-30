CREATE DATABASE IF NOT EXISTS elibrary;
USE elibrary;

-- Create book_categories table first
CREATE TABLE IF NOT EXISTS book_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARBINARY(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    authors VARCHAR(255),
    description TEXT,
    cover_image VARCHAR(255),
    preview_link VARCHAR(255),
    source ENUM('admin', 'openlibrary', 'gutenberg') DEFAULT 'admin',
    category_id INT,
    price DECIMAL(10, 2) DEFAULT 29.99,
    added_by INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES book_categories(id),
    FOREIGN KEY (added_by) REFERENCES users(id)
);

-- Orders table (moved before borrowed_books)
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    total_amount DECIMAL(10, 2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    payment_details TEXT NOT NULL,
    order_type ENUM('purchase', 'borrow') DEFAULT 'purchase',
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Order items table
CREATE TABLE IF NOT EXISTS order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    book_id INT NOT NULL,
    quantity INT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(id),
    FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE TABLE IF NOT EXISTS borrowed_books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    book_id INT NOT NULL,
    order_id INT NOT NULL,
    borrow_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    due_date TIMESTAMP NOT NULL,
    return_date TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (book_id) REFERENCES books(id),
    FOREIGN KEY (order_id) REFERENCES orders(id)
);

CREATE TABLE IF NOT EXISTS purchased_books (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    book_id INT NOT NULL,
    purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (book_id) REFERENCES books(id)
);

-- Cart table
CREATE TABLE IF NOT EXISTS cart_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    book_id INT NOT NULL,
    quantity INT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (book_id) REFERENCES books(id)
);

CREATE TABLE IF NOT EXISTS refunds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    borrow_id INT NOT NULL,
    amount DECIMAL(10, 2) NOT NULL,
    refund_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    reason VARCHAR(255) NOT NULL,
    FOREIGN KEY (borrow_id) REFERENCES borrowed_books(id)
);

-- Create admin_logs table
CREATE TABLE IF NOT EXISTS admin_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,
    action_type ENUM(
        'ADD_BOOK', 'EDIT_BOOK', 'DELETE_BOOK',
        'ADD_USER', 'EDIT_USER', 'DELETE_USER', 'MAKE_ADMIN',
        'TOGGLE_USER_STATUS',
        'ADD_CATEGORY', 'EDIT_CATEGORY', 'DELETE_CATEGORY'
    ) NOT NULL,
    target_id INT,
    details TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (admin_id) REFERENCES users(id)
);

-- Insert default categories
INSERT INTO book_categories (name, description) VALUES
('Fiction', 'Novels, short stories, and other fictional works'),
('Non-Fiction', 'Educational and informative books based on facts'),
('Science', 'Books about scientific discoveries and concepts'),
('Technology', 'Books about computers, programming, and technology'),
('History', 'Books about historical events and figures'),
('Business', 'Books about business, finance, and entrepreneurship'),
('Arts', 'Books about art, music, and creative pursuits'),
('Self-Help', 'Books for personal development and growth');

-- Insert default admin user (username: admin, password: admin123)
INSERT INTO users (username, email, password, is_admin) 
VALUES ('admin', 'admin@elibrary.com', SHA2('admin123', 256), TRUE);

-- Insert default normal user (username: user, password: user123)
INSERT INTO users (username, email, password, is_admin)
VALUES ('user', 'user@elibrary.com', SHA2('user123', 256), FALSE);
