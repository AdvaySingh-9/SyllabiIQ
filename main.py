import shutil
import sqlite3
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

import database
import extractor
import vision
import rag

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_ROOT = BASE_DIR / "uploads"

# Home page
@app.route("/")
def index():
    rooms = database.get_all_rooms()
    return render_template("home.html", rooms=rooms)



# CHAT TAB
@app.route("/chat", methods=["GET", "POST"])
def chat():
    room_id = request.args.get("room", type=int)
    room = database.get_room(room_id) if room_id else None
    return render_template("chat.html", room=room)


# GENERATE TAB
@app.route("/generate")
def generate():
    room_id = request.args.get("room", type=int)
    room = database.get_room(room_id) if room_id else None
    return render_template("generate.html", room=room)


# MEMORY TAB
@app.route("/memory")
def memory():
    room_id = request.args.get("room", type=int)
    room = database.get_room(room_id) if room_id else None
    resources = database.get_resources(room_id) if room_id else []
    return render_template("memory.html", room=room, resources=resources)


# Creating a room with name of chapter and subject
@app.route("/create_room", methods=["POST"])
def create_room():
    name = request.form.get("name", "").strip()
    subject = request.form.get("subject", "").strip()

    if not name or not subject:
        return jsonify({"error": "Please provide a chapter name and its subject."}), 400

    # save the chapter room in database
    room_id = database.create_chapter_room(name, subject)
    return jsonify({"success": True, "room_id": room_id}), 201


# delete the room
@app.route('/delete-room/<int:room_id>', methods=['POST'])
def delete_room(room_id):
    try:
        # delete room from the database
        database.delete_room(room_id)
    except Exception as exc:
        return jsonify({"error": f"Unable to delete room: {exc}"}), 500

    # delete room from folder (with resources)
    room_folder = UPLOAD_ROOT / f"room_{room_id}"
    if room_folder.exists():
        shutil.rmtree(room_folder, ignore_errors=True)

    return jsonify({"success": True})


# upload pdf function
@app.route("/upload_pdf", methods=["POST"])
def upload_pdf():
    pdf = request.files.get("pdf")
    room_id_raw = request.form.get("room_id")

    if not pdf:
        return jsonify({"error": "No PDF uploaded"}), 400

    if not room_id_raw:
        return jsonify({"error": "Please select a chapter room before uploading."}), 400

    try:
        room_id = int(room_id_raw)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid room id."}), 400

    # get the all the things from room with room_id 
    room = database.get_room(room_id)
    if room is None:
        return jsonify({"error": "Selected room was not found."}), 404

    room_folder = UPLOAD_ROOT / f"room_{room_id}"
    images_folder = room_folder / "images"
    room_folder.mkdir(parents=True, exist_ok=True)
    images_folder.mkdir(parents=True, exist_ok=True)

    original_filename = secure_filename(pdf.filename) or "chapter.pdf"
    pdf_filename = original_filename
    pdf_path = room_folder / pdf_filename

    try:
        pdf.save(pdf_path)
    except Exception as e:
        return jsonify({"error": f"Unable to save uploaded PDF: {e}"}), 500

    resource_id = None
    try:
        
        # saving the pdf in 'uploads' folder with room_id & pdf name 
        resource_id = database.save_resource(room_id, pdf_filename, f"uploads/room_{room_id}/{pdf_filename}")
        extracted_pages = extractor.extract_content(str(pdf_path))

        # save the page content in page_content table (only text)
        for page in extracted_pages:
            page_number = int(page.get("page_number", 0))
            database.save_page_content(room_id, resource_id, page_number, page.get("text", ""))

            # saving the images in folder & page_images table
            for image_index, image_data in enumerate(page.get("images", []), start=1):
                extension = image_data.get("extension", "png") or "png"
                image_filename = f"page_{page_number}_img_{image_index}.{extension}"
                image_path = images_folder / image_filename
                image_path.write_bytes(image_data.get("bytes", b""))
                image_db_path = f"uploads/room_{room_id}/images/{image_filename}"
                try:
                    image_description = vision.get_image_description(str(image_path))
                except Exception as exc:
                    # If vision fails for this image, continue processing remaining images.
                    image_description = f"Vision error: {exc}"

                database.save_page_image(room_id, resource_id, page_number, image_db_path, image_description)

        room_id = int(room_id_raw)
        rag.index_pdf(room_id=room_id, resource_id=resource_id)

        return jsonify({
            "message": "PDF uploaded successfully",
        }), 201
    except (sqlite3.Error, RuntimeError) as exc:
        if resource_id is not None:
            try:
                database.delete_resource(resource_id)
            except Exception:
                pass
        return jsonify({"error": f"Processing failed: {exc}"}), 500
    except Exception as exc:
        if resource_id is not None:
            try:
                database.delete_resource(resource_id)
            except Exception:
                pass
        return jsonify({"error": f"Unexpected upload failure: {exc}"}), 500

# displaying the uploaded PDFs in memory tab
@app.route("/uploads/room_<int:room_id>/<path:filename>")
def uploaded_file(room_id, filename):
    folder = str(UPLOAD_ROOT / f"room_{room_id}")
    return send_from_directory(folder, filename)


@app.route("/chat/room_<int:room_id>/ask")
def ask(room_id):
    # Read the question from query parameters (GET). Keep the route unchanged.
    question = request.args.get("question") or request.args.get("q")
    if not question:
        return {"error": "Missing 'question' parameter"}, 400

    answer = rag.generate_answer(question, room_id)

    return {"answer": answer}

# running the app on default browser
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=7860)