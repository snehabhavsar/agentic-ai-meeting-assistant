import os

# Load .env from backend/ or repo root so DEEPGRAM_API_KEY / GEMINI_API_KEY work
try:
    from dotenv import load_dotenv
    _backend_dir = os.path.dirname(os.path.abspath(__file__))
    _root_dir = os.path.dirname(_backend_dir)
    load_dotenv(os.path.join(_backend_dir, ".env"))
    load_dotenv(os.path.join(_root_dir, ".env"))
except ImportError:
    pass

from app import create_app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False, threaded=True)

