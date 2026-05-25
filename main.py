"""
Entry point — always uses the professional engine in app.py.

Do NOT use the legacy bot/ package (removed).
Run: python main.py   OR   python app.py
"""

from app import app, config

if __name__ == "__main__":
    print(f"BTC Pro Terminal (engine v2): http://127.0.0.1:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=False)
