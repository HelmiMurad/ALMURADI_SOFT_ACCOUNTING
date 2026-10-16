"""Run the Flask app in a native desktop window using pywebview."""
import os
import threading
import time
import webbrowser
from werkzeug.serving import make_server
from app import app, init_db

HOST = '127.0.0.1'
PORT = int(os.environ.get('LOCAL_WEB_PORT', '8765'))
URL = f'http://{HOST}:{PORT}'

class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.server = make_server(HOST, PORT, app, threaded=True)
    def run(self): self.server.serve_forever()
    def stop(self): self.server.shutdown()

def main():
    try:
        import webview
    except ImportError:
        print('pywebview is not installed. Run RUN_DESKTOP.bat to install it.')
        webbrowser.open(URL)
        from app import app as flask_app
        flask_app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
        return
    init_db()
    server = ServerThread()
    server.start()
    time.sleep(0.6)
    try:
        webview.create_window('M-ERP | المرادي سوفت', URL,
                              width=1440, height=900, min_size=(1050, 680),
                              text_select=True, confirm_close=True)
        webview.start()
    finally:
        server.stop()

if __name__ == '__main__': main()
