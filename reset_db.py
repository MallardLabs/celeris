import os
from dotenv import load_dotenv
from database import init_db

load_dotenv()

def main():
    db_url = os.getenv("DATABASE_URL", "sqlite:///your_database.db")
    init_db(db_url)
    print("Database reset successfully!")

if __name__ == "__main__":
    main() 