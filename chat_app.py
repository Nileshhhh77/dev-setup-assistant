import os
import base64
import io
import sqlite3
import chainlit as cl
from groq import Groq
import httpx
import pytesseract
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
OCR_ENGINE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(OCR_ENGINE):
    pytesseract.pytesseract.tesseract_cmd = OCR_ENGINE


def extract_image_text(raw_image):
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw_image)) as image:
            image.load()
            image.thumbnail((2400, 2400), Image.Resampling.LANCZOS)
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            text = pytesseract.image_to_string(image)
            return text.strip()
    except Exception as error:
        print(f"Image OCR error: {error}")
        return ""


def extract_document_text(raw_file, filename, mime_type):
    extension = os.path.splitext(filename)[1].lower()
    try:
        if extension == ".pdf" or mime_type == "application/pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw_file))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()

        if extension == ".docx":
            from docx import Document
            document = Document(io.BytesIO(raw_file))
            paragraphs = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    paragraphs.append(" | ".join(cell.text for cell in row.cells))
            return "\n".join(paragraphs).strip()

        if extension == ".xlsx":
            from openpyxl import load_workbook
            workbook = load_workbook(io.BytesIO(raw_file), read_only=True, data_only=True)
            lines = []
            for sheet in workbook.worksheets:
                lines.append(f"Sheet: {sheet.title}")
                for row in sheet.iter_rows(values_only=True):
                    lines.append(" | ".join("" if value is None else str(value) for value in row))
            return "\n".join(lines).strip()

        if extension == ".pptx":
            from pptx import Presentation
            presentation = Presentation(io.BytesIO(raw_file))
            lines = []
            for index, slide in enumerate(presentation.slides, start=1):
                lines.append(f"Slide {index}")
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text.strip():
                        lines.append(shape.text.strip())
            return "\n".join(lines).strip()

        if extension in {".zip"} or mime_type == "application/zip":
            import zipfile
            with zipfile.ZipFile(io.BytesIO(raw_file)) as archive:
                lines = []
                for member in archive.infolist():
                    if member.is_dir() or member.file_size > 2_000_000:
                        continue
                    if any(member.filename.lower().endswith(ext) for ext in (".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".py", ".js", ".ts", ".html", ".css", ".log")):
                        try:
                            lines.append(f"--- {member.filename} ---\n{archive.read(member).decode('utf-8-sig', errors='replace')}")
                        except Exception:
                            pass
                return "\n".join(lines).strip()

        if extension in {".tar", ".tgz", ".tar.gz"} or mime_type in {"application/x-tar", "application/gzip"}:
            import tarfile
            with tarfile.open(fileobj=io.BytesIO(raw_file), mode="r:*") as archive:
                lines = []
                for member in archive.getmembers():
                    if not member.isfile() or member.size > 2_000_000:
                        continue
                    source = archive.extractfile(member)
                    if source:
                        lines.append(f"--- {member.name} ---\n{source.read().decode('utf-8-sig', errors='replace')}")
                return "\n".join(lines).strip()

        if (mime_type and mime_type.startswith("text/")) or mime_type == "application/json" or extension:
            decoded = raw_file[:5_000_000].decode("utf-8-sig", errors="replace")
            if decoded and "\x00" not in decoded:
                return decoded.strip()
    except Exception as error:
        print(f"Document extraction error for {filename}: {error}")
    return ""


def get_groq_client():
    global groq_client
    if groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not configured")
        http_client = httpx.Client(
            timeout=httpx.Timeout(45.0, connect=20.0),
            limits=httpx.Limits(max_connections=3, max_keepalive_connections=1),
            trust_env=False,
        )
        groq_client = Groq(api_key=api_key, http_client=http_client, timeout=45.0, max_retries=2)
    return groq_client

# --- LOGIN CALLBACK ---
@cl.password_auth_callback
def auth_callback(username: str, password: str):
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = ?", (username.strip().lower(),))
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
        cl.Starter(label="Analyze a file", message="I will upload a screenshot, PDF, text file, source code, or other document about an installation problem. Please inspect every supported attachment and explain how to fix it."),
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
    image_text = ""
    document_texts = []
    if message.elements:
        for element in message.elements:
            filename = getattr(element, "name", "attachment") or "attachment"
            raw_file = None
            if hasattr(element, 'content') and element.content:
                raw_file = element.content
            elif hasattr(element, 'path') and element.path:
                with open(element.path, "rb") as attachment:
                    raw_file = attachment.read()

            if element.mime and element.mime.startswith("image/") and raw_file:
                image_text = extract_image_text(raw_file)
                try:
                    from PIL import Image
                    with Image.open(io.BytesIO(raw_file)) as image:
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
                    base64_image = base64.b64encode(raw_file).decode("utf-8")
                    image_data = f"data:{element.mime};base64,{base64_image}"
            elif raw_file:
                extracted = extract_document_text(raw_file, filename, element.mime)
                if extracted:
                    document_texts.append(f"--- {filename} ---\n{extracted[:12000]}")
                else:
                    document_texts.append(f"--- {filename} ---\nBinary or unsupported attachment received ({len(raw_file)} bytes). Do not claim that its contents were inspected. Ask the user to upload an extractable format or paste the relevant content.")

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
    if document_texts:
        document_prompt = query or "Analyze the attached documents and help with the requested task."
        document_prompt += "\n\nAttached file contents:\n" + "\n\n".join(document_texts)
        messages_for_groq.append({"role": "user", "content": document_prompt})
        model_to_use = "openai/gpt-oss-120b"
    elif image_data:
        image_prompt = query or "Analyze the setup or error shown in this screenshot."
        if image_text:
            image_prompt += f"\n\nText extracted from the attached screenshot:\n{image_text[:4000]}"
        else:
            image_prompt += "\n\nOCR could not extract readable text. Ask for the exact error message and a clear description of the visible content if needed."
        messages_for_groq.append({"role": "user", "content": image_prompt})
        model_to_use = "openai/gpt-oss-120b"
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
        print(f"Groq API error ({model_to_use}) [{type(e).__name__}]: {e}")
        if image_data:
            answer = "⚠️ The AI service could not process this image. Please verify the Groq API key, internet connection, and that the selected vision model is enabled for your account."
        else:
            answer = "⚠️ The AI service is temporarily unreachable. Please check the local internet connection and Groq API key, then try again."

    # 6. Save text memory
    history.append({"role": "user", "content": query})
    history.append({"role": "assistant", "content": answer})
    history = history[-12:]
    cl.user_session.set("history", history)

    # 7. Send response
    await cl.Message(content=answer).send()