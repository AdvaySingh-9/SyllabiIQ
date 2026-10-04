import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.environ.get("SYLLABIIQ_DB_PATH", str(BASE_DIR / "syllabiiq.db"))

# setting the encoding to uft-8 (ONLY FOR DEBUGGING)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# connecting to SQLight database
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# Creating every table in the database
def initialize_schema(conn: sqlite3.Connection) -> None:
    
    # creating rooms table to store all the chapter rooms with unique id, name of chapter and subject
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS rooms(
            id INTEGER PRIMARY KEY,
            name TEXT,
            subject TEXT
        )
        """
    )

    # creating resources table to store pdf with id, room id, file name and file path
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS resources(
            id INTEGER PRIMARY KEY,
            room_id INTEGER,
            file_name TEXT,
            file_path TEXT
        )
        """
    )

    # creating page_content table to store the content of given pdf with id, room id, resource id, page number and page content (only text will be save in this table)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS page_content(
            id INTEGER PRIMARY KEY,
            room_id INTEGER,
            resource_id INTEGER,
            page_number INTEGER,
            page_content TEXT
        )
        """
    )

    # creating page_images table to store images/diagrams of book/pdf with id, room id, resource id, page number and image path and AI-generated image description(the images will not be saved only its path will be saved and the images will be in the uploads folder in respective room id)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS page_images(
            id INTEGER PRIMARY KEY,
            room_id INTEGER,
            resource_id INTEGER,
            page_number INTEGER,
            image_path TEXT,
            image_description TEXT
        )
        """
    )


# function to create room
def create_chapter_room(name: str, subject: str) -> int:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO rooms (name, subject) VALUES (?, ?)",
            (name, subject),
        )
        room_id = cursor.lastrowid
        conn.commit()
        return int(room_id)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to create room: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()

# function to save resources
def save_resource(room_id: int, file_name: str, file_path: str) -> int:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO resources (room_id, file_name, file_path) VALUES (?, ?, ?)",
            (room_id, secure_filename(file_name) or "chapter.pdf", file_path),
        )
        resource_id = cursor.lastrowid
        conn.commit()
        return int(resource_id)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to save resource: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()

def save_resources(room_id: int, file) -> int:
    file_name = getattr(file, "filename", "") or "chapter.pdf"
    file_path = os.path.join("uploads", f"room_{room_id}", secure_filename(file_name) or "chapter.pdf")
    return save_resource(room_id, file_name, file_path)

# function to display all the rooms in home page
def get_all_rooms():
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms")
        return cursor.fetchall()
    finally:
        if conn is not None:
            conn.close()

# get all the content of room using its id
def get_room(room_id: int):
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM rooms WHERE id = ?", (room_id,))
        return cursor.fetchone()
    finally:
        if conn is not None:
            conn.close()

# function to get the resources
def get_resources(room_id: int):
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, file_name, file_path
            FROM resources
            WHERE room_id = ?
            """,
            (room_id,),
        )
        return cursor.fetchall()
    finally:
        if conn is not None:
            conn.close()

# function to save the text from PDF in page_content table page-by-page (ONLY TEXT)
def save_page_content(room_id: int, resource_id: int, page_number: int, page_content: str) -> int:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO page_content (room_id, resource_id, page_number, page_content)
            VALUES (?, ?, ?, ?)
            """,
            (room_id, resource_id, page_number, page_content),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to save page content: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


# function to save images path of the PDFs page-by-page 
def save_page_image(
    room_id: int,
    resource_id: int,
    page_number: int,
    image_path: str,
    image_description: Optional[str] = None,
) -> int:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO page_images (room_id, resource_id, page_number, image_path, image_description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (room_id, resource_id, page_number, image_path, image_description),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to save page image: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()



def get_page_content(room_id: int, resource_id: Optional[int] = None):
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        if resource_id is None:
            cursor.execute(
                "SELECT * FROM page_content WHERE room_id = ? ORDER BY page_number",
                (room_id,),
            )
        else:
            cursor.execute(
                "SELECT * FROM page_content WHERE room_id = ? AND resource_id = ? ORDER BY page_number",
                (room_id, resource_id),
            )
        return cursor.fetchall()
    finally:
        if conn is not None:
            conn.close()


def get_page_images(room_id: int, resource_id: Optional[int] = None):
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        if resource_id is None:
            cursor.execute(
                "SELECT * FROM page_images WHERE room_id = ? ORDER BY page_number",
                (room_id,),
            )
        else:
            cursor.execute(
                "SELECT * FROM page_images WHERE room_id = ? AND resource_id = ? ORDER BY page_number",
                (room_id, resource_id),
            )
        return cursor.fetchall()
    finally:
        if conn is not None:
            conn.close()


def delete_room(room_id: int) -> None:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM page_images WHERE room_id = ?", (room_id,))
        cursor.execute("DELETE FROM page_content WHERE room_id = ?", (room_id,))
        cursor.execute("DELETE FROM resources WHERE room_id = ?", (room_id,))
        cursor.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to delete room: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()

#function to delete resources with room id

def delete_resource(resource_id: int) -> None:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM page_images WHERE resource_id = ?", (resource_id,))
        cursor.execute("DELETE FROM page_content WHERE resource_id = ?", (resource_id,))
        cursor.execute("DELETE FROM resources WHERE id = ?", (resource_id,))
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to delete resource: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()


def delete_resources() -> None:
    conn = None
    try:
        conn = get_connection()
        initialize_schema(conn)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM page_images")
        cursor.execute("DELETE FROM page_content")
        cursor.execute("DELETE FROM resources")
        conn.commit()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.rollback()
        raise RuntimeError(f"Unable to delete resources: {exc}") from exc
    finally:
        if conn is not None:
            conn.close()



# CHECKING THE SAVED CONTENT (ONLY FOR DEBUGGING)
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def show_tables():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print("Tables:")
    for row in tables:
        print(" -", row["name"])
    conn.close()


def show_all_rows():
    conn = get_connection()
    cursor = conn.cursor()

    tables = ["rooms", "resources", "page_content", "page_images"]

    for table in tables:
        print(f"\n=== {table} ===")
        try:
            cursor.execute(f"SELECT * FROM {table}")
            rows = cursor.fetchall()
            if not rows:
                print("(empty)")
            else:
                for row in rows:
                    print(dict(row))
        except Exception as e:
            print("Error:", e)

    conn.close()


def show_rooms():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rooms")
    rows = cursor.fetchall()
    print("\n=== rooms ===")
    for row in rows:
        print(dict(row))
    conn.close()


def show_resources(room_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    if room_id is None:
        cursor.execute("SELECT * FROM resources")
    else:
        cursor.execute("SELECT * FROM resources WHERE room_id = ?", (room_id,))

    rows = cursor.fetchall()
    print("\n=== resources ===")
    for row in rows:
        print(dict(row))
    conn.close()


def show_page_content(room_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    if room_id is None:
        cursor.execute("SELECT * FROM page_content")
    else:
        cursor.execute("SELECT * FROM page_content WHERE room_id = ?", (room_id,))

    rows = cursor.fetchall()
    print("\n=== page_content ===")
    for row in rows:
        print(dict(row))
    conn.close()


def show_page_images(room_id=None):
    conn = get_connection()
    cursor = conn.cursor()

    if room_id is None:
        cursor.execute("SELECT * FROM page_images")
    else:
        cursor.execute("SELECT * FROM page_images WHERE room_id = ?", (room_id,))

    rows = cursor.fetchall()
    print("\n=== page_images ===")
    for row in rows:
        print(dict(row))
    conn.close()

"""
show_tables()
show_all_rows()
show_page_content(2)
show_page_images(1)

"""

"""
images = get_page_images(room_id=2)
for img in images:
    print(f"Page {img['page_number']} → Path: {img['image_path']}, Description: {img['image_description']}")"""