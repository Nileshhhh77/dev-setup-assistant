import os
import base64
import io
import sqlite3
import chainlit as cl
from groq import Groq
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

# Disable Chainlit's built-in DB saving to prevent errors
os.environ["DATABASE_URL"] = ""

# --- DATABASE & AUTH SETUP ---
USER_DB = os.path.join(os.path.dirname(__file__), "users.db")
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def get_db_connection():
    conn = sqlite3.connect(USER_DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_user_db():
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (username TEXT PRIMARY KEY, password_hash TEXT)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database connection error: {e}")

init_user_db()

# --- CONNECT TO SERVICES ---
groq_client = None


def get_groq_client():
    global groq_client
    if groq_client is None:
        groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return groq_client

# --- LOGIN CALLBACK ---
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        result = c.fetchone()
        conn.close()

        if result:
            stored_hash = result[0]
            if pwd_context.verify(password, stored_hash):
                return cl.User(identifier=username, metadata={"role": "user"})
    except Exception as e:
        print(f"Auth error: {e}")

    return None

# --- CHAT EXPERIENCE ---
@cl.set_chat_profiles
async def set_chat_profiles():
    common = "I use this operating system for setup instructions and commands."
    return [
        cl.ChatProfile(name="Windows", display_name="Windows workspace", markdown_description=common, default=True),
        cl.ChatProfile(name="macOS", display_name="macOS workspace", markdown_description=common),
        cl.ChatProfile(name="Linux", display_name="Linux workspace", markdown_description=common),
    ]

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(label="Install a tool", message="Help me install Python on my computer. Give me the exact steps and verify the installation."),
        cl.Starter(label="Fix an error", message="I have an installation or setup error. Ask me for the exact error message, operating system, and command I ran."),
        cl.Starter(label="Create a project", message="Guide me through creating a clean development project. Ask about the language, operating system, and tools I need."),
        cl.Starter(label="Analyze an image", message="I will upload a screenshot or photo of an installation problem. Please inspect it and explain how to fix it."),
    ]

# --- CHAT LOGIC ---
@cl.on_chat_start
async def start():
    cl.user_session.set("history", [])
    profile = cl.user_session.get("chat_profile") or "Windows"
    await cl.Message(
        content=f"## How can I help you set up your workspace?\n"
                f"You’re using the **{profile}** profile. Ask for install steps, paste an error, or upload a screenshot.\n\n"
                "### Quick options\n"
                "- Install Python, Node.js, Git, Java, or C++\n"
                "- Diagnose a setup error\n"
                "- Open the [Installation Guides](/guides)\n\n"
                "<small>Tip: Include the exact command and error message for the fastest answer.</small>"
    ).send()

@cl.on_chat_resume
async def on_chat_resume(thread):
    await cl.Message(content="Welcome back! Let's continue where we left off.").send()

@cl.on_message
async def main(message: cl.Message):
    query = message.content
    history = cl.user_session.get("history") or []
    
    # Keep retrieval lightweight on free hosting; use the Groq model directly.
    context = ""

    # 1. Check for uploaded images
    image_data = None
    if message.elements:
        for element in message.elements:
            if element.mime and element.mime.startswith("image/"):
                raw_image = None
                if hasattr(element, 'content') and element.content:
                    raw_image = element.content
                elif hasattr(element, 'path') and element.path:
                    with open(element.path, "rb") as image_file:
                        raw_image = image_file.read()

                if raw_image:
                    try:
                        from PIL import Image
                        with Image.open(io.BytesIO(raw_image)) as image:
                            image.load()
                            image.thumbnail((1568, 1568), Image.Resampling.LANCZOS)
                            if image.mode not in ("RGB", "L"):
                                image = image.convert("RGB")
                            output = io.BytesIO()
                            image.save(output, format="JPEG", quality=85, optimize=True)
                            base64_image = base64.b64encode(output.getvalue()).decode("utf-8")
                            image_data = f"data:image/jpeg;base64,{base64_image}"
                    except Exception as image_error:
                        print(f"Image preparation error: {image_error}")
                        base64_image = base64.b64encode(raw_image).decode("utf-8")
                        image_data = f"data:{element.mime};base64,{base64_image}"
                break

    # 2. Build a focused, user-friendly system prompt
    profile = cl.user_session.get("chat_profile") or "Windows"
    system_content = f"""You are a calm, precise developer setup assistant.
The user's selected operating system is {profile}. Always give commands for this system unless they explicitly ask for another one.
Structure installation answers as: goal, prerequisites, numbered steps, verification command, and common fixes.
Use clear headings and short paragraphs. Never claim a command succeeded without a verification result.
If information is missing or ambiguous, ask one focused follow-up question rather than guessing.
For troubleshooting, ask for or explain the exact error, operating system, tool version, and command that was run.
Use this verified knowledge when relevant:
{context if context else "No local knowledge match was found; use careful general guidance."}"""

    # 3. Build the messages for Groq
    messages_for_groq = [{"role": "system", "content": system_content}]
    
    # Add text history (Groq needs this to be standard text format)
    for msg in history:
        messages_for_groq.append({"role": msg["role"], "content": msg["content"]})
        
    # Build the current user message
    if image_data:
        # If there's an image, we use the multimodal format ONLY for the current message
        user_content = [
            {"type": "text", "text": query},
            {"type": "image_url", "image_url": {"url": image_data}}
        ]
        messages_for_groq.append({"role": "user", "content": user_content})
        model_to_use = "meta-llama/llama-4-scout-17b-16e-instruct"
    else:
        messages_for_groq.append({"role": "user", "content": query})
        model_to_use = "openai/gpt-oss-120b"

    # 5. Call Groq
    try:
        completion = get_groq_client().chat.completions.create(
            model=model_to_use,
            messages=messages_for_groq,
            max_tokens=1024
        )
        answer = completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API error ({model_to_use}): {e}")
        if image_data:
            try:
                fallback_messages = messages_for_groq[:-1] + [{
                    "role": "user",
                    "content": f"{query}\n\n[An image was attached, but vision processing is temporarily unavailable. Ask for a clear description or screenshot details before diagnosing.]"
                }]
                completion = get_groq_client().chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=fallback_messages,
                    max_tokens=1024
                )
                answer = completion.choices[0].message.content
            except Exception as fallback_error:
                print(f"Groq fallback error: {fallback_error}")
                answer = "⚠️ The AI service could not process the message right now. Please try a smaller image again, or send the text from the screenshot."
        else:
            answer = "⚠️ The AI service could not complete this request right now. Please try again."

    # 6. Save text memory
    history.append({"role": "user", "content": query})
    history.append({"role": "assistant", "content": answer})
    history = history[-12:]
    cl.user_session.set("history", history)

    # 7. Send response
    await cl.Message(content=answer).send()