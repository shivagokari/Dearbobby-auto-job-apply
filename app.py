import os
import sys
import json
import csv
import subprocess
import threading
from flask import Flask, jsonify, request, render_template, send_from_directory
from werkzeug.utils import secure_filename
from resume_parser import parse_resume

app = Flask(__name__, template_folder="templates", static_folder="static")

# Execution State Variables
proc = None
console_logs = []
log_lock = threading.Lock()
proc_thread = None

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(WORKSPACE_ROOT, "profile.json")
LOG_PATH = os.path.join(WORKSPACE_ROOT, "applied_log.csv")

def read_process_output(p):
    """
    Reads subprocess stdout line by line and appends to in-memory log list.
    """
    global console_logs
    # Keep reading until process terminates
    for line in iter(p.stdout.readline, ""):
        with log_lock:
            console_logs.append(line)
            # Limit memory logs to last 500 lines
            if len(console_logs) > 500:
                console_logs.pop(0)
    p.stdout.close()
    p.wait()
    with log_lock:
        console_logs.append(f"\n[SYSTEM] Assistant terminated with exit code {p.returncode}.\n")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/profile", methods=["GET", "POST"])
def manage_profile():
    if request.method == "GET":
        if not os.path.exists(PROFILE_PATH):
            return jsonify({"error": "Profile template does not exist."}), 404
        try:
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data)
        except Exception as e:
            return jsonify({"error": f"Failed to read profile: {e}"}), 500
            
    elif request.method == "POST":
        try:
            new_data = request.json
            if not new_data:
                return jsonify({"error": "No data provided."}), 400
                
            # Write formatting matches profile.json template
            with open(PROFILE_PATH, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2)
            return jsonify({"message": "Profile updated successfully."})
        except Exception as e:
            return jsonify({"error": f"Failed to save profile: {e}"}), 500

@app.route("/api/logs", methods=["GET"])
def get_logs():
    if not os.path.exists(LOG_PATH):
        return jsonify([])
        
    logs = []
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                logs.append(row)
        # Return newest logs first
        return jsonify(list(reversed(logs)))
    except Exception as e:
        return jsonify({"error": f"Failed to parse log file: {e}"}), 500

@app.route("/api/upload-resume", methods=["POST"])
def upload_resume():
    if "resume" not in request.files:
        return jsonify({"error": "No file part in the request."}), 400
        
    file = request.files["resume"]
    if file.filename == "":
        return jsonify({"error": "No file selected."}), 400
        
    filename = file.filename.lower()
    if filename.endswith(".pdf"):
        target_name = "resume.pdf"
    elif filename.endswith(".docx") or filename.endswith(".doc"):
        target_name = "resume.docx"
    else:
        return jsonify({"error": "Unsupported file format. Only PDF and DOCX files are allowed."}), 400
        
    try:
        file.save(os.path.join(WORKSPACE_ROOT, target_name))
        # Remove any other formats to avoid confusion
        other_format = "resume.docx" if target_name == "resume.pdf" else "resume.pdf"
        other_path = os.path.join(WORKSPACE_ROOT, other_format)
        if os.path.exists(other_path):
            os.remove(other_path)
            
        return jsonify({"message": f"Successfully uploaded and saved as {target_name}"})
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {e}"}), 500

@app.route("/api/run", methods=["POST"])
def start_runner():
    global proc, console_logs, proc_thread
    if proc and proc.poll() is None:
        return jsonify({"error": "Assistant is already running."}), 400
        
    with log_lock:
        console_logs = [f"[SYSTEM] Starting automation runner at {request.host}...\n"]
        
    try:
        # Run main.py using python, with unbuffered output (-u) so we capture live outputs instantly
        # Execute it in the same environment and directory
        proc = subprocess.Popen(
            [sys.executable, "-u", "main.py"],
            cwd=WORKSPACE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        proc_thread = threading.Thread(target=read_process_output, args=(proc,), daemon=True)
        proc_thread.start()
        
        return jsonify({"status": "started"})
    except Exception as e:
        return jsonify({"error": f"Failed to start process: {e}"}), 500

@app.route("/api/stop", methods=["POST"])
def stop_runner():
    global proc
    if not proc or proc.poll() is not None:
        return jsonify({"error": "Assistant is not running."}), 400
        
    try:
        # Terminate process tree
        proc.terminate()
        # Give it a second to shutdown gracefully, otherwise kill
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            
        return jsonify({"status": "stopped"})
    except Exception as e:
        return jsonify({"error": f"Failed to stop process: {e}"}), 500

@app.route("/api/status", methods=["GET"])
def run_status():
    global proc, console_logs
    is_running = proc is not None and proc.poll() is None
    
    with log_lock:
        logs_copy = list(console_logs)
        
    # Check what resume is currently uploaded in the workspace
    resume_file = "None"
    if os.path.exists(os.path.join(WORKSPACE_ROOT, "resume.pdf")):
        resume_file = "resume.pdf"
    elif os.path.exists(os.path.join(WORKSPACE_ROOT, "resume.docx")):
        resume_file = "resume.docx"
        
    return jsonify({
        "running": is_running,
        "logs": "".join(logs_copy),
        "resume": resume_file
    })

@app.route("/api/resume-keywords", methods=["GET"])
def get_resume_keywords():
    resume_path = None
    possible_resumes = ["resume.pdf", "resume.docx", "resume.doc"]
    for pr in possible_resumes:
        path = os.path.join(WORKSPACE_ROOT, pr)
        if os.path.exists(path):
            resume_path = path
            break
            
    if not resume_path:
        return jsonify([])
        
    try:
        _, keywords = parse_resume(resume_path)
        return jsonify(list(keywords))
    except Exception as e:
        return jsonify({"error": f"Failed to parse resume: {e}"}), 500

@app.route("/api/import-cookies", methods=["POST"])
def import_cookies():
    try:
        raw_data = request.json
        if not raw_data:
            return jsonify({"error": "No data provided."}), 400
            
        # If user pasted the cookie array directly, or a dict containing cookies
        if isinstance(raw_data, list):
            cookies_list = raw_data
        elif isinstance(raw_data, dict) and "cookies" in raw_data:
            cookies_list = raw_data["cookies"]
        else:
            return jsonify({"error": "Invalid cookie format. Please paste a JSON array."}), 400
            
        # Format cookies to match Playwright specifications
        formatted_cookies = []
        for cookie in cookies_list:
            if "name" in cookie and "value" in cookie:
                formatted_cookies.append({
                    "name": cookie["name"],
                    "value": cookie["value"],
                    "domain": cookie.get("domain", ".naukri.com"),
                    "path": cookie.get("path", "/"),
                    "expires": cookie.get("expirationDate") or cookie.get("expires") or -1,
                    "httpOnly": cookie.get("httpOnly", False),
                    "secure": cookie.get("secure", False),
                    "sameSite": cookie.get("sameSite", "Lax")
                })
                
        # Write storage state
        playwright_session = {
            "cookies": formatted_cookies,
            "origins": []
        }
        
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(playwright_session, f, indent=2)
            
        print("Successfully imported Naukri session cookies.")
        return jsonify({"message": "Cookies imported successfully."})
    except Exception as e:
        return jsonify({"error": f"Failed to import cookies: {e}"}), 500

HANDSHAKE_FILE = os.path.join(WORKSPACE_ROOT, "login_handshake.json")

@app.route("/api/login-handshake", methods=["GET"])
def get_login_handshake():
    if not os.path.exists(HANDSHAKE_FILE):
        return jsonify({"status": "none"})
    try:
        with open(HANDSHAKE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})

@app.route("/api/submit-credentials", methods=["POST"])
def submit_credentials():
    data = request.json or {}
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        return jsonify({"error": "Username and password are required."}), 400
        
    try:
        with open(HANDSHAKE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "status": "credentials_submitted",
                "username": username,
                "password": password
            }, f, indent=2)
        return jsonify({"message": "Credentials submitted."})
    except Exception as e:
        return jsonify({"error": f"Failed to submit credentials: {e}"}), 500

@app.route("/api/submit-otp", methods=["POST"])
def submit_otp():
    data = request.json or {}
    otp = data.get("otp")
    if not otp:
        return jsonify({"error": "OTP is required."}), 400
        
    try:
        with open(HANDSHAKE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "status": "otp_submitted",
                "otp": otp
            }, f, indent=2)
        return jsonify({"message": "OTP submitted."})
    except Exception as e:
        return jsonify({"error": f"Failed to submit OTP: {e}"}), 500

@app.route("/api/submit-mobile", methods=["POST"])
def submit_mobile():
    data = request.json or {}
    mobile = data.get("mobile")
    if not mobile:
        return jsonify({"error": "Mobile number is required."}), 400
        
    try:
        with open(HANDSHAKE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "status": "mobile_submitted",
                "mobile": mobile
            }, f, indent=2)
        return jsonify({"message": "Mobile number submitted."})
    except Exception as e:
        return jsonify({"error": f"Failed to submit mobile number: {e}"}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    session_file = os.path.join(WORKSPACE_ROOT, "naukri_session.json")
    if os.path.exists(session_file):
        try:
            os.remove(session_file)
        except Exception as e:
            return jsonify({"error": f"Failed to delete session file: {e}"}), 500
            
    # Also delete the login_handshake if it exists
    if os.path.exists(HANDSHAKE_FILE):
        try:
            os.remove(HANDSHAKE_FILE)
        except Exception:
            pass
            
    return jsonify({"message": "Successfully logged out from Naukri. Session cookies deleted."})

if __name__ == "__main__":
    print("DearBobby Automation Web Dashboard starting...")
    print("Access locally at: http://127.0.0.1:5000")
    print("Access on your mobile phone (on same Wi-Fi) at: http://192.168.50.232:5000")
    # Bind to 0.0.0.0 to allow mobile/external network connections
    app.run(host="0.0.0.0", port=5000, debug=True)
