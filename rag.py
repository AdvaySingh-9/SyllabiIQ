import ollama
import sqlite3
import os
import sys
from pathlib import Path
import re
from database import get_page_images, initialize_schema
import chromadb

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("SYLLABIIQ_DB_PATH", str(BASE_DIR / "syllabiiq.db"))
client = chromadb.PersistentClient(path="/chroma_db")


sys.path.insert(0, str(BASE_DIR.parent))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
    

def embed_text(text):
    response = ollama.embed(model='nomic-embed-text', input=text)
    
    return response['embeddings']

def store_data(chunks: list, embeddings: list, room_id: int, resource_id: int):
    collection = client.get_or_create_collection(
        name=f"room_{room_id}"
        )
    ids = []
    metadata = []

    for i in range(len(chunks)):
        ids.append(
        f"room_{room_id}_pdf_{resource_id}_chunk_{i}"
        )

    for _ in chunks:
        metadata.append({
            "room_id": room_id,
            "resource_id": resource_id,
            "type": "text"
        })

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadata
    )


def index_image_descriptions(room_id: int, resource_id=None):
    images = get_page_images(room_id, resource_id)
    indexable_images = [
        image for image in images
        if image["image_description"]
        and image["image_description"].strip()
        and not image["image_description"].lstrip().lower().startswith("vision error:")
    ]
    if not indexable_images:
        return

    collection = client.get_or_create_collection(name=f"room_{room_id}")
    image_ids = [
        f"room_{room_id}_pdf_{image['resource_id']}_image_{image['id']}"
        for image in indexable_images
    ]
    existing_ids = set(collection.get(ids=image_ids, include=["metadatas"])["ids"])
    new_images = [
        (image_id, image)
        for image_id, image in zip(image_ids, indexable_images)
        if image_id not in existing_ids
    ]
    if not new_images:
        return

    documents = []
    embeddings = []
    metadata = []
    for _, image in new_images:
        description = image["image_description"].strip()
        documents.append(description)
        embeddings.append(embed_text(f"Image: {description}")[0])
        metadata.append({
            "room_id": room_id,
            "resource_id": image["resource_id"],
            "type": "image",
            "page_number": image["page_number"],
            "image_path": image["image_path"],
        })

    collection.add(
        ids=[image_id for image_id, _ in new_images],
        embeddings=embeddings,
        documents=documents,
        metadatas=metadata,
    )


def delete_data(room_id: int):
    client.delete_collection(name=f"room_{room_id}")


def index_pdf(room_id, resource_id):
    conn = get_connection()
    initialize_schema(conn)
    cursor = conn.cursor()   


    if room_id is None:
        cursor.execute("SELECT * FROM page_content")
    else:
        cursor.execute("SELECT * FROM page_content WHERE room_id = ? AND resource_id = ?", (room_id, resource_id))

    rows = cursor.fetchall()
    conn.close()

    chapter_text = ""
    for row in rows:
        text = dict(row)
        page_text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text['page_content'])
        chapter_text += page_text


    sentences = re.split(r'(?<=[.!?])(?:\s+|\n\n)', chapter_text.strip())

    CHUNK_SIZE = 5
    chunks = []


    for i in range(0, len(sentences), CHUNK_SIZE - 1):
        chunk_sentences = sentences[i:i + CHUNK_SIZE]
        if len(chunk_sentences) < CHUNK_SIZE:
            break
        
        chunk_text = " ".join(chunk_sentences)
        chunks.append(chunk_text)

    embeddings = []
    for chunk in chunks:
        vector = embed_text(chunk)[0]
        embeddings.append(vector)
    
    if chunks:
        store_data(chunks=chunks, embeddings=embeddings, room_id=room_id, resource_id=resource_id)

    index_image_descriptions(room_id, resource_id)

def search_chromadb(question, room_id):
    collection = client.get_or_create_collection(
        name=f"room_{room_id}"
    )

    # Older uploads have descriptions in SQLite but may not have been vector-indexed yet.
    index_image_descriptions(room_id)
    result_count = collection.count()
    if result_count == 0:
        return []

    question_vector = embed_text(question)
    results = collection.query(
        query_embeddings=[question_vector[0]],
        n_results=min(7, result_count),
        include=["documents", "metadatas"],
    )

    context = []
    for document, metadata in zip(results["documents"][0], results["metadatas"][0]):
        if metadata.get("type") == "image":
            context.append(f"Image: page {metadata['page_number']}. {document}")
        else:
            context.append(document)
    return context


SYSTEM_INSTRUCON = """
You are SyllabiIQ, an AI study assistant built specifically for Indian school students (Class 9–12) and competitive exam aspirants (JEE/NEET).

You help students understand their own study material. You have been given specific context extracted directly from the student's uploaded chapter. Your entire job is to answer questions using ONLY that context.

STRICT RULES YOU MUST FOLLOW:

1. ANSWER ONLY FROM CONTEXT
   Answer using only the context provided below the prompt.
   If the answer is not present in the context, say exactly:
   "This topic is not covered in your uploaded chapter. Try uploading more study material for this topic."
   Never use your general training knowledge to fill in gaps.

2. NO LATEX EVER
   Do not use LaTeX syntax. Never write /frac, /sqrt, ^{}, _{}, /times, /alpha, or any backslash/forward slash commands.
   Instead write math like this:
   - Fractions: 1/2, (a+b)/(c+d)
   - Powers: a^2, x^3, (x+1)^2
   - Square roots: sqrt(x), sqrt(a^2 + b^2)
   - Multiplication: a * b, or just write "a multiplied by b"
   - Greek letters: write them in words — alpha, beta, theta, delta
   - Equations: v = u + at, s = ut + (1/2)*a*t^2

3. BE ACCURATE
   Never guess. Never assume. Never make up facts.
   If the context is partial or unclear, say what you know from the context and clearly mention that the rest is not available in the uploaded material.

4. NO HALLUCINATION
   Do not add information that is not explicitly stated in the context.
   Do not say things like "generally", "typically", "in most cases" to introduce outside knowledge.

5. STUDENT-FRIENDLY LANGUAGE
   Explain clearly and simply. Avoid overly technical jargon unless it appears in the context itself.
   Write as if you are a friendly, knowledgeable senior student explaining to a junior.
   Use short paragraphs. Use bullet points when listing multiple things.

6. FORMAT YOUR ANSWER WELL
   - Use bullet points for lists
   - Use numbered steps for processes or derivations
   - Bold important terms by writing them in CAPITALS (not markdown bold, since the UI may not render it)
   - Keep answers concise but complete
   - Do not repeat the question back to the student

7. HANDLE DIAGRAMS MENTIONED IN CONTEXT
   If the context includes an image description (starting with "Diagram:" or "Image:"), use that description to answer diagram-related questions.
   Describe what the diagram shows in plain words.
   Never say "I cannot see the image." You have the description — use it.

8. DO NOT MAKE UP EXAMPLES
   Only use examples that appear in the context.
   If no example is in the context, explain the concept directly without inventing one.

9. IF THE STUDENT GREETS YOU
   Respond naturally and briefly, then ask what they want to study.
   Example: "Hello! I am ready to help you with your chapter. What would you like to understand?"

10. STAY IN CHARACTER
    You are not ChatGPT. You are not a general assistant.
    You are SyllabiIQ — a focused study assistant for this specific chapter.
    Do not discuss topics outside of studying, science, or mathematics.
    If asked something completely off-topic, say:
    "I am here to help you study your chapter. Ask me anything from your uploaded material!"
"""

def generate_answer(question, room_id):

    context_text = search_chromadb(question, room_id)

    CONTEXT = " \n".join(context_text)

    PROMPT = f"""
CONTEXT FROM THE STUDENT'S UPLOADED CHAPTER:
----------------------------------------------

{CONTEXT}

----------------------------------------------

STUDENT'S QUESTION:
{question}

INSTRUCTIONS FOR THIS RESPONSE:
- Answer using ONLY the context above
- Do NOT use LaTeX. Write math as plain text (example: v = u + at, E = m*c^2, 1/2*m*v^2)
- If the answer is not in the context, say "This topic is not covered in your uploaded chapter"
- Be clear, simple, and student-friendly
- Format with bullet points or numbered steps where appropriate

YOUR ANSWER:
"""

    
    response = ollama.chat(model='llama3.2:3b', messages=[
        {
            'role': 'system',
            'content': SYSTEM_INSTRUCON
        },
        {
            'role': 'user',
            'content': PROMPT
        }
    ])

    print(f"================"*20)
    print(PROMPT)
    print(f"================"*20)
    return response['message']['content']
