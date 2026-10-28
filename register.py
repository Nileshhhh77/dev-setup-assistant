import sqlite3
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
USER_DB = "users.db"

def register_user():
    username = input("Enter new username (or email): ")
    password = input("Enter password: ")
    
    hashed = pwd_context.hash(password[:72])
    
    try:
        conn = sqlite3.connect(USER_DB)
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
        conn.commit()
        conn.close()
        print(f"✅ User '{username}' created successfully!")
    except sqlite3.IntegrityError:
        print("❌ Username already exists.")

if __name__ == "__main__":
    register_user()