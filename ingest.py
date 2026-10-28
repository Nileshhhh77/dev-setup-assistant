import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

# Connect to your Qdrant Cloud Database
client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))

# This model turns text into numbers so the AI can search it
model = SentenceTransformer("all-MiniLM-L6-v2")

# Our tiny knowledge base
docs = [
    "To install Python on Windows, download the installer from python.org, check 'Add Python to PATH' during installation.",
    "To install Node.js on macOS, run: brew install node. Then verify with node -v.",
    "To install Java JDK on Ubuntu, run: sudo apt update && sudo apt install openjdk-17-jdk.",
]

# Create the collection in Qdrant
client.recreate_collection(
    collection_name="dev_setup",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
)

# Convert text to vectors and upload
points = [
    PointStruct(id=i, vector=model.encode(doc).tolist(), payload={"text": doc})
    for i, doc in enumerate(docs)
]
client.upsert(collection_name="dev_setup", points=points)
print("Ingestion complete! Knowledge base is ready.")