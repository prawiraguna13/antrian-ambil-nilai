import unittest
import os
import json
import urllib.request
import urllib.error
import threading
import socketserver
import time
import server

TEST_PORT = 8999

class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use an isolated test database
        cls.orig_db = server.DB_FILE
        server.DB_FILE = os.path.join(os.path.dirname(__file__), "test_antrian.db")
        if os.path.exists(server.DB_FILE):
            os.remove(server.DB_FILE)
        server.init_db()

        # Start a test server in a daemon thread
        cls.httpd = server.ThreadedDatabaseServer(("127.0.0.1", TEST_PORT), server.AntrianDatabaseHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.DB_FILE = cls.orig_db
        test_db = os.path.join(os.path.dirname(__file__), "test_antrian.db")
        for f in [test_db, f"{test_db}-wal", f"{test_db}-shm"]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except OSError:
                    pass

    def test_01_blocked_database_download(self):
        """Verifies GET /test_antrian.db or /antrian.db is forbidden (403)."""
        url = f"http://127.0.0.1:{TEST_PORT}/test_antrian.db"
        req = urllib.request.Request(url)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_02_unauthenticated_admin_endpoint_rejected(self):
        """Verifies admin POST without token returns 401."""
        url = f"http://127.0.0.1:{TEST_PORT}/api/queue/call-next"
        req = urllib.request.Request(
            url,
            data=json.dumps({"score": 90}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 401)

    def test_03_login_and_authenticated_action(self):
        """Verifies login succeeds with token, and authenticated action works."""
        # 1. Login
        login_url = f"http://127.0.0.1:{TEST_PORT}/api/auth/login"
        req = urllib.request.Request(
            login_url,
            data=json.dumps({"username": "kien", "password": "123!@#"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        data = json.loads(res.read().decode("utf-8"))
        self.assertTrue(data.get("success"))
        token = data.get("token")
        self.assertTrue(bool(token))

        # 2. Add class with token
        add_url = f"http://127.0.0.1:{TEST_PORT}/api/classes/add"
        req2 = urllib.request.Request(
            add_url,
            data=json.dumps({"name": "Test Class A"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        res2 = urllib.request.urlopen(req2)
        data2 = json.loads(res2.read().decode("utf-8"))
        self.assertTrue(data2.get("success"))

    def test_04_student_registration_sequence(self):
        """Verifies student registration produces sequential queue numbers."""
        reg_url = f"http://127.0.0.1:{TEST_PORT}/api/register"
        req = urllib.request.Request(
            reg_url,
            data=json.dumps({"nama": "Budi", "kelas": "XII RPL 1", "materi": "VLAN"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res = urllib.request.urlopen(req)
        data = json.loads(res.read().decode("utf-8"))
        self.assertTrue(data.get("success"))
        self.assertEqual(data["student"]["code"], "#A-01")

        req2 = urllib.request.Request(
            reg_url,
            data=json.dumps({"nama": "Siti", "kelas": "XII RPL 2", "materi": "VLAN"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        res2 = urllib.request.urlopen(req2)
        data2 = json.loads(res2.read().decode("utf-8"))
        self.assertTrue(data2.get("success"))
        self.assertEqual(data2["student"]["code"], "#A-02")

if __name__ == "__main__":
    unittest.main()
