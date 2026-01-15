# -*- coding: utf-8 -*-
"""
修復 jobs 表 - 添加缺失的 input_audio_path 欄位
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.utils import load_env
load_env()

import mysql.connector

db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", "3306"))
db_user = os.getenv("DB_USER", "studio_user")
db_password = os.getenv("DB_PASSWORD", "studio_password")
db_name = os.getenv("DB_NAME", "studio_db")

print(f"Connecting to: {db_user}@{db_host}:{db_port}/{db_name}")

conn = mysql.connector.connect(
    host=db_host,
    port=db_port,
    user=db_user,
    password=db_password,
    database=db_name
)
cursor = conn.cursor()

# 檢查欄位是否存在
print("\n[1] Checking if 'input_audio_path' column exists...")
cursor.execute("""
    SELECT COLUMN_NAME 
    FROM INFORMATION_SCHEMA.COLUMNS 
    WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'jobs' AND COLUMN_NAME = 'input_audio_path'
""", (db_name,))
exists = cursor.fetchone()

if exists:
    print("    Column 'input_audio_path' already exists. No action needed.")
else:
    print("    Column 'input_audio_path' NOT found. Adding it now...")
    cursor.execute("""
        ALTER TABLE jobs 
        ADD COLUMN input_audio_path VARCHAR(255) DEFAULT NULL
    """)
    conn.commit()
    print("    [OK] Column 'input_audio_path' added successfully!")

cursor.close()
conn.close()
print("\nDone.")
