import sqlite3

db_path = "AllPrintings.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get a distinct list of all formats in the database
query = "SELECT DISTINCT cardLegalities;"

cursor.execute(query)
formats = cursor.fetchall()

for fmt in formats:
    print(fmt[0])

conn.close()
