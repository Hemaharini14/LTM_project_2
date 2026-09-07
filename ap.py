import sqlite3

conn = sqlite3.connect("edubridge.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE universities(
    id INTEGER PRIMARY KEY,
    university_name TEXT,
    country TEXT,
    qs_rank INTEGER,
    tuition_fee REAL,
    living_cost REAL,
    course_name TEXT
)
""")

conn.commit()
conn.close()