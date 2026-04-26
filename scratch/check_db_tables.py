import os
import sqlite3
import sys

# Try to find scar directory
sys.path.append(os.getcwd())

from scar import data_store

print(f"DB Path from data_store: {data_store.DB_PATH}")
print(f"File exists: {os.path.exists(data_store.DB_PATH)}")

try:
    conn = sqlite3.connect(data_store.DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables found: {[t[0] for t in tables]}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")
