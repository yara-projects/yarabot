"""Create shared role-access tables without changing existing school data."""

import mysql.connector

from config import DB_CONFIG


conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_sections (
        class VARCHAR(10) PRIMARY KEY,
        school_section ENUM('boys','girls') NOT NULL
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS parents (
        parent_id INT PRIMARY KEY AUTO_INCREMENT,
        name VARCHAR(100) NOT NULL,
        contact VARCHAR(15)
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS parent_student_links (
        parent_id INT NOT NULL,
        student_id INT NOT NULL,
        PRIMARY KEY (parent_id, student_id),
        FOREIGN KEY (parent_id) REFERENCES parents(parent_id),
        FOREIGN KEY (student_id) REFERENCES students(student_id)
    )
""")
cursor.execute("""
    ALTER TABLE users MODIFY role
    ENUM('student','parent','teacher','hod','vice_principal','assistant_principal','principal','admin')
""")
conn.commit()
cursor.close()
conn.close()
print("class_sections is ready; assign classes in the dashboard.")
