import os
import sqlite3
import sys

import util

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def generateCsvForSpider(baseDir):
    # Define the paths for the database and test_database directories
    database_dir = os.path.join(baseDir, 'database')
    test_database_dir = os.path.join(baseDir, 'test_database')

    # Function to process each database directory
    def process_database_dir(db_dir, csv_dir):
        for db_name in os.listdir(db_dir):
            db_path = os.path.join(db_dir, db_name, f"{db_name}.sqlite")
            if os.path.isfile(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [item[0] for item in cursor.fetchall()]

                for table_name in tables:
                    cursor.execute(f"PRAGMA table_info({table_name});")
                    columns = [info[1] for info in cursor.fetchall()]

                    csv_path = os.path.join(csv_dir, db_name, f"{table_name.lower()}.csv")
                    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
                    util.generate_csv(csv_path, db_path, table_name, columns)

                conn.close()

    # Process the database and test_database directories
    process_database_dir(database_dir, os.path.join(baseDir, 'csv', 'database'))
    process_database_dir(test_database_dir, os.path.join(baseDir, 'csv', 'test_database'))

def generateCsvForBird(baseDir):
    # Define the paths for the database and test_database directories
    # database_dir = os.path.join(baseDir, 'train', 'train_databases')
    test_database_dir = os.path.join(baseDir, 'dev_20240627', 'dev_databases_ori')

    # Function to process each database directory
    def process_database_dir(db_dir, csv_dir):
        for db_name in os.listdir(db_dir):
            db_path = os.path.join(db_dir, db_name, f"{db_name}.sqlite")
            if os.path.isfile(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = [item[0] for item in cursor.fetchall()]

                for table_name in tables:
                    print(csv_dir, db_name, table_name)
                    cursor.execute(f"PRAGMA table_info('{table_name}');")
                    columns = [info[1] for info in cursor.fetchall()]

                    csv_path = os.path.join(csv_dir, db_name, f"{table_name.lower()}.csv")
                    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
                    util.generate_csv(csv_path, db_path, table_name, columns)

                conn.close()

    # Process the database and test_database directories
    process_database_dir(test_database_dir, os.path.join(baseDir, 'dev_20240627', 'csv', 'dev_databases_ori'))
    # process_database_dir(database_dir, os.path.join(baseDir, 'train', 'csv', 'train_databases'))

