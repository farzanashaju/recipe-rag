import importlib.util
import threading
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
BUILD_RAG_PATH = BASE_DIR.parent / "scripts" / "build-rag.py"


def load_recipe_rag_class():
    """Load RecipeRAG from build-rag.py."""
    spec = importlib.util.spec_from_file_location("build_rag_module", BUILD_RAG_PATH)

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.RecipeRAG


RecipeRAG = load_recipe_rag_class()

app = Flask(__name__, template_folder="templates", static_folder="static")

rag = RecipeRAG(
    json_dir=str(BASE_DIR.parent / "data" / "swiggy_recipe_json"),
    db_dir=str(BASE_DIR.parent / "data" / "recipe_db_local"),
    llm_model="llama3.2",
    retrieval_k=5,
)


def _warm_up():
    """Pre-load CLIP model and vector store in background."""
    print("Warming up")
    rag.build_index()
    print("Warmup complete")


threading.Thread(target=_warm_up, daemon=True, name="rag-warmup").start()


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("message", "")).strip()
    image_b64 = payload.get("image")
    history = payload.get("history", [])

    if not question and not image_b64:
        return jsonify({"error": "Message or image is required."}), 400

    try:
        response = rag.query(question=question, image_b64=image_b64, history=history)
        answer = response.get("result", "No response returned.")
        return jsonify({"answer": answer})
    except Exception as exc:
        return jsonify({"error": f"Failed to process query: {exc}"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True, use_reloader=False)
