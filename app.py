import os
import sqlite3
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from chainlit.utils import mount_chainlit
from passlib.context import CryptContext
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles

load_dotenv()

app = FastAPI()
USER_DB = os.path.join(os.path.dirname(__file__), "users.db")
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def get_db_connection():
    conn = sqlite3.connect(USER_DB)
    return conn


def init_user_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (username TEXT PRIMARY KEY, password_hash TEXT)''')
    conn.commit()
    conn.close()


init_user_db()

PUBLIC_DIR = os.path.join(os.path.dirname(__file__), "public")
app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


class SignupModel(BaseModel):
    username: str
    password: str


class LoginModel(BaseModel):
    username: str
    password: str


@app.post("/api/signup")
async def signup(data: SignupModel):
    try:
        if len(data.username.strip()) < 3 or "@" not in data.username:
            return JSONResponse(status_code=400, content={"detail": "Enter a valid email address."})
        if len(data.password) < 8:
            return JSONResponse(status_code=400, content={"detail": "Password must be at least 8 characters."})

        conn = get_db_connection()
        c = conn.cursor()

        c.execute("SELECT username FROM users WHERE username = ?", (data.username.strip(),))
        if c.fetchone():
            conn.close()
            return JSONResponse(status_code=400, content={"detail": "Email already registered."})

        hashed = pwd_context.hash(data.password[:72])
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (data.username.strip(), hashed))
        conn.commit()
        conn.close()

        return JSONResponse(content={"message": "User created successfully"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/login")
async def login(data: LoginModel):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = ?", (data.username.strip(),))
        result = c.fetchone()
        conn.close()

        if result and pwd_context.verify(data.password, result[0]):
            return JSONResponse(content={"message": "Login successful"})

        return JSONResponse(status_code=401, content={"detail": "Invalid username or password."})
    except Exception as e:
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.get("/signup")
async def serve_signup():
    try:
        with open(os.path.join(PUBLIC_DIR, "signup.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Signup page not found.</h1>")


@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})

@app.get("/login")
async def serve_login():
    try:
        with open(os.path.join(PUBLIC_DIR, "login.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Login page not found.</h1>")


@app.get("/guides")
async def serve_guides():
    try:
        with open(os.path.join(PUBLIC_DIR, "guides.html"), "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Guides page not found.</h1>")

@app.get("/")
async def home():
    return RedirectResponse(url="/chat")

# Mount the chat app from chat_app.py
mount_chainlit(app=app, target="chat_app.py", path="/chat")