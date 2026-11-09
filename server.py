import http.server
import socketserver
import json
import sqlite3
import os
import urllib.parse
import time
import hashlib
import secrets
from datetime import datetime

PORT = 8000
DB_FILE = os.path.join(os.path.dirname(__file__), "antrian.db")
PUBLIC_DIR = os.path.dirname(__file__)

ACTIVE_TOKENS = set()

def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()
    
    # 1. Admin Credentials Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_user (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Default admin credentials (hashed)
    c.execute("SELECT password FROM admin_user WHERE id = 1")
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO admin_user (id, username, password) VALUES (1, 'kien', ?)", (hash_pw('123!@#'),))
    elif len(row[0]) != 64:  # migrate unhashed plaintext password
        c.execute("UPDATE admin_user SET password = ? WHERE id = 1", (hash_pw(row[0]),))

    # 2. Classes Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("SELECT COUNT(*) FROM classes")
    if c.fetchone()[0] == 0:
        defaults = ['XII RPL 1', 'XII RPL 2', 'XII TKJ 1', 'XII TKJ 2']
        c.executemany("INSERT OR IGNORE INTO classes (name) VALUES (?)", [(d,) for d in defaults])

    # 3. Topics Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("SELECT COUNT(*) FROM topics")
    if c.fetchone()[0] == 0:
        defaults = [
            'Routing MikroTik & VLAN',
            'CRUD REST API Laravel',
            'Desain UI Glassmorphism & Tailwind',
            'Fiber Optic Splicing & OTDR'
        ]
        c.executemany("INSERT OR IGNORE INTO topics (title) VALUES (?)", [(d,) for d in defaults])

    # 4. Queue & Assessment History Table
    c.execute("""
        CREATE TABLE IF NOT EXISTS student_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            num INTEGER NOT NULL,
            code TEXT NOT NULL,
            nama TEXT NOT NULL,
            kelas TEXT NOT NULL,
            materi TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'waiting', -- waiting, in_progress, completed, skipped
            nilai REAL DEFAULT NULL,
            kelulusan TEXT DEFAULT NULL, -- Lulus, Ulang, Dilewati
            catatan TEXT DEFAULT '',
            registered_at TEXT NOT NULL,
            started_at INTEGER DEFAULT NULL,
            completed_at TEXT DEFAULT NULL,
            last_called_at TIMESTAMP DEFAULT NULL,
            call_count INTEGER DEFAULT 0
        )
    """)

    # 5. System Event Table (for TTS Voice Broadcasts across devices)
    c.execute("""
        CREATE TABLE IF NOT EXISTS call_events (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            code TEXT,
            nama TEXT,
            call_timestamp INTEGER
        )
    """)
    c.execute("SELECT COUNT(*) FROM call_events WHERE id = 1")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO call_events (id, code, nama, call_timestamp) VALUES (1, '', '', 0)")

    conn.commit()
    conn.close()

class AntrianDatabaseHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def is_authorized(self):
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            return token in ACTIVE_TOKENS
        return False

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Block access to database, python, shell, and hidden files
        clean_path = path.lstrip("/")
        if clean_path.endswith((".db", ".py", ".sh", ".md", ".json")) or ".." in path or clean_path.startswith("."):
            self.send_error(403, "Forbidden")
            return

        # Single-Page Application (SPA) routes
        if path in ["/", "/siswa", "/guru", "/admin", "/antrian", "/display"]:
            self.serve_file(os.path.join(PUBLIC_DIR, "index.html"), "text/html; charset=utf-8")
            return
        elif path == "/api/bootstrap":
            self.handle_bootstrap()
            return
        elif path == "/api/export-excel":
            query_params = urllib.parse.parse_qs(parsed.query)
            token = query_params.get("token", [""])[0]
            auth_header = self.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            if token not in ACTIVE_TOKENS:
                self.send_json({"error": "Unauthorized: Login guru diperlukan untuk mengunduh rekap"}, status=401)
                return
            self.handle_export_excel()
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            data = {}

        # Admin-only endpoints protection
        ADMIN_ENDPOINTS = {
            "/api/auth/update",
            "/api/classes/add",
            "/api/classes/delete",
            "/api/classes/clear",
            "/api/topics/add",
            "/api/topics/delete",
            "/api/topics/clear",
            "/api/queue/call-next",
            "/api/queue/recall",
            "/api/queue/clear",
            "/api/history/delete",
            "/api/history/clear",
        }
        if path in ADMIN_ENDPOINTS and not self.is_authorized():
            self.send_json({"success": False, "message": "Akses ditolak: Memerlukan login guru"}, status=401)
            return

        if path == "/api/register":
            self.handle_register(data)
        elif path == "/api/auth/login":
            self.handle_login(data)
        elif path == "/api/auth/logout":
            token = self.headers.get("Authorization", "").replace("Bearer ", "").strip()
            ACTIVE_TOKENS.discard(token)
            self.send_json({"success": True, "message": "Logout berhasil"})
        elif path == "/api/auth/update":
            self.handle_update_auth(data)
        elif path == "/api/classes/add":
            self.handle_add_class(data)
        elif path == "/api/classes/delete":
            self.handle_delete_class(data)
        elif path == "/api/classes/clear":
            self.handle_clear_classes()
        elif path == "/api/topics/add":
            self.handle_add_topic(data)
        elif path == "/api/topics/delete":
            self.handle_delete_topic(data)
        elif path == "/api/topics/clear":
            self.handle_clear_topics()
        elif path == "/api/queue/call-next":
            self.handle_call_next(data)
        elif path == "/api/queue/recall":
            self.handle_recall()
        elif path == "/api/queue/clear":
            self.handle_clear_queue()
        elif path == "/api/history/delete":
            self.handle_delete_history(data)
        elif path == "/api/history/clear":
            self.handle_clear_history()
        else:
            self.send_json({"error": "Endpoint tidak ditemukan"}, status=404)

    def send_json(self, payload, status=200):
        response = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(response)

    def serve_file(self, filepath, content_type):
        if not os.path.exists(filepath):
            self.send_error(404, "File Not Found")
            return
        with open(filepath, "rb") as f:
            content = f.read()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(content)

    # 1. Bootstrap: Fetch entire state from database
    def handle_bootstrap(self):
        conn = get_db()
        c = conn.cursor()

        # Admin username
        c.execute("SELECT username FROM admin_user WHERE id = 1")
        admin_row = c.fetchone()
        admin_username = admin_row["username"] if admin_row else "kien"

        # Classes
        c.execute("SELECT name FROM classes ORDER BY id ASC")
        classes = [r["name"] for r in c.fetchall()]

        # Topics
        c.execute("SELECT title FROM topics ORDER BY id ASC")
        topics = [r["title"] for r in c.fetchall()]

        # Active student currently in_progress
        c.execute("""
            SELECT id, num, code, nama, kelas, materi, started_at
            FROM student_queue
            WHERE status = 'in_progress'
            ORDER BY id DESC LIMIT 1
        """)
        cur_row = c.fetchone()
        current_student = dict(cur_row) if cur_row else None

        # Waiting queue
        c.execute("""
            SELECT id, num, code, nama, kelas, materi, registered_at
            FROM student_queue
            WHERE status = 'waiting'
            ORDER BY id ASC
        """)
        queue = [dict(r) for r in c.fetchall()]

        # Graded history (completed or skipped)
        c.execute("""
            SELECT id, num, code, nama, kelas, materi, nilai, kelulusan as status, catatan, completed_at as completedAt
            FROM student_queue
            WHERE status IN ('completed', 'skipped')
            ORDER BY id DESC
        """)
        history = [dict(r) for r in c.fetchall()]

        # Last call event for TTS audio triggers
        c.execute("SELECT code, nama, call_timestamp FROM call_events WHERE id = 1")
        event_row = c.fetchone()
        last_call_event = dict(event_row) if event_row else None

        conn.close()

        self.send_json({
            "success": True,
            "admin": {"username": admin_username},
            "classes": classes,
            "topics": topics,
            "current_student": current_student,
            "queue": queue,
            "history": history,
            "last_call_event": last_call_event,
            "server_time": int(time.time() * 1000)
        })

    # 2. Register Student
    def handle_register(self, data):
        nama = (data.get("nama") or "").strip()
        kelas = (data.get("kelas") or "").strip()
        materi = (data.get("materi") or "").strip()

        if not nama or not kelas or not materi:
            self.send_json({"success": False, "message": "Nama, Kelas, dan Materi wajib diisi!"}, status=400)
            return

        conn = get_db()
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT COALESCE(MAX(num), 0) + 1 FROM student_queue")
        next_num = c.fetchone()[0]
        code = f"#A-{next_num:02d}"
        registered_at = datetime.now().strftime("%H:%M")

        c.execute("""
            INSERT INTO student_queue (num, code, nama, kelas, materi, status, registered_at)
            VALUES (?, ?, ?, ?, ?, 'waiting', ?)
        """, (next_num, code, nama, kelas, materi, registered_at))
        student_id = c.lastrowid
        conn.commit()
        conn.close()

        self.send_json({
            "success": True,
            "message": "Pendaftaran berhasil disimpan ke database!",
            "student": {
                "id": student_id,
                "num": next_num,
                "code": code,
                "nama": nama,
                "kelas": kelas,
                "materi": materi,
                "registered_at": registered_at
            }
        })

    # 3. Auth Check
    def handle_login(self, data):
        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        hashed = hash_pw(password)

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM admin_user WHERE id = 1 AND username = ? AND password = ?", (username, hashed))
        row = c.fetchone()
        conn.close()

        if row:
            token = secrets.token_hex(16)
            ACTIVE_TOKENS.add(token)
            self.send_json({"success": True, "token": token, "message": "Login berhasil"})
        else:
            self.send_json({"success": False, "message": "Username atau password salah!"}, status=401)

    # 4. Update Auth
    def handle_update_auth(self, data):
        new_user = (data.get("username") or "").strip()
        new_pass = data.get("password") or ""

        if not new_user or not new_pass:
            self.send_json({"success": False, "message": "Username dan password tidak boleh kosong!"}, status=400)
            return

        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE admin_user 
            SET username = ?, password = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (new_user, hash_pw(new_pass)))
        conn.commit()
        conn.close()

        self.send_json({"success": True, "message": "Kredensial admin di database berhasil diperbarui!"})

    # 5. Class Management
    def handle_add_class(self, data):
        name = (data.get("name") or "").strip()
        if not name:
            self.send_json({"success": False, "message": "Nama kelas tidak boleh kosong!"}, status=400)
            return
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO classes (name) VALUES (?)", (name,))
            conn.commit()
            conn.close()
            self.send_json({"success": True, "message": f"Kelas '{name}' berhasil disimpan ke database!"})
        except sqlite3.IntegrityError:
            conn.close()
            self.send_json({"success": False, "message": "Kelas tersebut sudah ada di database!"}, status=400)

    def handle_delete_class(self, data):
        name = (data.get("name") or "").strip()
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM classes WHERE name = ?", (name,))
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": f"Kelas '{name}' dihapus dari database!"})

    def handle_clear_classes(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM classes")
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": "Semua kelas berhasil dihapus dari database!"})

    # 6. Topic Management
    def handle_add_topic(self, data):
        title = (data.get("title") or "").strip()
        if not title:
            self.send_json({"success": False, "message": "Judul materi tidak boleh kosong!"}, status=400)
            return
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO topics (title) VALUES (?)", (title,))
            conn.commit()
            conn.close()
            self.send_json({"success": True, "message": f"Materi '{title}' berhasil disimpan ke database!"})
        except sqlite3.IntegrityError:
            conn.close()
            self.send_json({"success": False, "message": "Materi tersebut sudah ada di database!"}, status=400)

    def handle_delete_topic(self, data):
        title = (data.get("title") or "").strip()
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM topics WHERE title = ?", (title,))
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": f"Materi '{title}' dihapus dari database!"})

    def handle_clear_topics(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM topics")
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": "Semua materi berhasil dihapus dari database!"})

    # 7. Queue: Call Next Student & Grade Active
    def handle_call_next(self, data):
        conn = get_db()
        c = conn.cursor()

        # Check if there is an in_progress student currently
        c.execute("SELECT id FROM student_queue WHERE status = 'in_progress' LIMIT 1")
        active = c.fetchone()

        if active:
            active_id = active["id"]
            skip = data.get("skip_current", False)
            score = data.get("score")
            status_val = data.get("status", "Lulus")
            notes = (data.get("notes") or "").strip()
            completed_time = datetime.now().strftime("%H:%M")

            if skip or score is None:
                c.execute("""
                    UPDATE student_queue
                    SET status = 'skipped', kelulusan = 'Dilewati', catatan = 'Dilewati tanpa nilai', completed_at = ?
                    WHERE id = ?
                """, (completed_time, active_id))
            else:
                try:
                    score_num = float(score)
                except ValueError:
                    score_num = 0.0
                c.execute("""
                    UPDATE student_queue
                    SET status = 'completed', nilai = ?, kelulusan = ?, catatan = ?, completed_at = ?
                    WHERE id = ?
                """, (score_num, status_val, notes, completed_time, active_id))

        # Pull next waiting student
        c.execute("SELECT id, num, code, nama, kelas, materi FROM student_queue WHERE status = 'waiting' ORDER BY id ASC LIMIT 1")
        next_student = c.fetchone()

        if not next_student:
            conn.commit()
            conn.close()
            self.send_json({"success": True, "message": "Antrian telah habis.", "student": None})
            return

        next_id = next_student["id"]
        start_time_ms = int(time.time() * 1000)

        c.execute("""
            UPDATE student_queue
            SET status = 'in_progress', started_at = ?, call_count = call_count + 1, last_called_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (start_time_ms, next_id))

        # Update call event so all listening displays trigger speech synthesis
        now_ts = int(time.time() * 1000)
        c.execute("""
            UPDATE call_events
            SET code = ?, nama = ?, call_timestamp = ?
            WHERE id = 1
        """, (next_student["code"], next_student["nama"], now_ts))

        conn.commit()
        conn.close()

        self.send_json({
            "success": True,
            "message": f"Memanggil antrian {next_student['code']} - {next_student['nama']}",
            "student": dict(next_student)
        })

    # 8. Recall current active student
    def handle_recall(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, code, nama FROM student_queue WHERE status = 'in_progress' LIMIT 1")
        row = c.fetchone()
        if not row:
            conn.close()
            self.send_json({"success": False, "message": "Tidak ada siswa aktif untuk dipanggil ulang."})
            return

        now_ts = int(time.time() * 1000)
        c.execute("UPDATE call_events SET code = ?, nama = ?, call_timestamp = ? WHERE id = 1", (row["code"], row["nama"], now_ts))
        c.execute("UPDATE student_queue SET call_count = call_count + 1, last_called_at = datetime('now', 'localtime') WHERE id = ?", (row["id"],))
        conn.commit()
        conn.close()

        self.send_json({"success": True, "message": f"Panggilan ulang untuk {row['code']} dikirimkan ke layar display!"})

    # 9. Clear Queue
    def handle_clear_queue(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM student_queue WHERE status IN ('waiting', 'in_progress')")
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": "Antrian aktif berhasil dibersihkan dari database!"})

    # 10. Delete History Item
    def handle_delete_history(self, data):
        student_id = data.get("id")
        if not student_id:
            self.send_json({"success": False, "message": "ID tidak valid"}, status=400)
            return
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM student_queue WHERE id = ?", (student_id,))
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": "Data riwayat nilai dihapus dari database!"})

    def handle_clear_history(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("DELETE FROM student_queue WHERE status IN ('completed', 'skipped')")
        conn.commit()
        conn.close()
        self.send_json({"success": True, "message": "Semua riwayat rekap nilai berhasil dibersihkan dari database!"})

    # 11. Export Excel XML (.xls)
    def handle_export_excel(self):
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT num, code, nama, kelas, materi, nilai, kelulusan, catatan, completed_at
            FROM student_queue
            WHERE status IN ('completed', 'skipped')
            ORDER BY id ASC
        """)
        rows = c.fetchall()
        conn.close()

        rows_html = ""
        for idx, r in enumerate(rows):
            nilai_str = str(r["nilai"]) if r["nilai"] is not None else "-"
            status_str = r["kelulusan"] or "-"
            catatan_str = r["catatan"] or "-"
            waktu_str = r["completed_at"] or "-"
            status_color = "#059669" if status_str == "Lulus" else "#dc2626"

            rows_html += f"""
            <tr>
              <td style="text-align: center; border: 1px solid #d1d5db; padding: 6px;">{idx + 1}</td>
              <td style="text-align: center; font-weight: bold; border: 1px solid #d1d5db; padding: 6px;">{r["code"]}</td>
              <td style="border: 1px solid #d1d5db; padding: 6px;">{r["nama"]}</td>
              <td style="border: 1px solid #d1d5db; padding: 6px;">{r["kelas"]}</td>
              <td style="border: 1px solid #d1d5db; padding: 6px;">{r["materi"]}</td>
              <td style="text-align: center; font-weight: bold; border: 1px solid #d1d5db; padding: 6px;">{nilai_str}</td>
              <td style="text-align: center; font-weight: bold; border: 1px solid #d1d5db; padding: 6px; color: {status_color};">{status_str}</td>
              <td style="border: 1px solid #d1d5db; padding: 6px;">{catatan_str}</td>
              <td style="text-align: center; border: 1px solid #d1d5db; padding: 6px;">{waktu_str}</td>
            </tr>
            """

        export_date = datetime.now().strftime("%d %B %Y, %H:%M")
        excel_template = f"""
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
        <head>
          <meta http-equiv="content-type" content="text/plain; charset=UTF-8"/>
          <style>
            th {{ background-color: #2563eb; color: #ffffff; font-weight: bold; text-align: center; border: 1px solid #1e40af; padding: 10px; }}
          </style>
        </head>
        <body>
          <h2 style="font-family: Arial, sans-serif; color: #1e1b4b;">REKAPITULASI NILAI UJIAN PRAKTIK SISWA</h2>
          <p style="font-family: Arial, sans-serif; font-size: 12px; color: #64748b;">Tanggal Export: {export_date}</p>
          <table style="border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px;" border="1">
            <thead>
              <tr>
                <th>No</th>
                <th>No. Antrian</th>
                <th>Nama Siswa</th>
                <th>Kelas</th>
                <th>Materi</th>
                <th>Nilai</th>
                <th>Status</th>
                <th>Catatan</th>
                <th>Waktu Selesai</th>
              </tr>
            </thead>
            <tbody>
              {rows_html}
            </tbody>
          </table>
        </body>
        </html>
        """.strip()

        raw_bytes = excel_template.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.ms-excel; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename=Rekap_Nilai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xls")
        self.send_header("Content-Length", str(len(raw_bytes)))
        self.end_headers()
        self.wfile.write(raw_bytes)

class ThreadedDatabaseServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

def run():
    init_db()
    server_address = ("", PORT)
    httpd = ThreadedDatabaseServer(server_address, AntrianDatabaseHandler)
    print(f"======================================================")
    print(f"🚀 SISTEM ANTRIAN PRAKTIK SISWA (SQLITE DATABASE AKTIF)")
    print(f"======================================================")
    print(f"📁 Database File            : {DB_FILE}")
    print(f"🌐 Akses Lokal (Komputer Ini): http://localhost:{PORT}/")
    print(f"🔑 Kredensial Default Guru  : kien / 123!@#")
    print(f"======================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()

if __name__ == "__main__":
    run()
