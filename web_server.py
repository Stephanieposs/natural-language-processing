"""Servidor local da demonstracao, com controle de atualizacao do acervo."""

import argparse
import json
import re
import subprocess
import sys
import threading
from datetime import date, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "scripts" / "atualizar_web.py"
SCHEDULE_CONFIG = ROOT / "data" / "processed" / "web_schedule.json"
schedule_lock = threading.Lock()


class Job:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.exit_code = None
        self.lines = []

    def start(self, args):
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.exit_code = None
            self.lines = ["Iniciando processamento..."]
        threading.Thread(target=self._run, args=(args,), daemon=True).start()
        return True

    def _run(self, args):
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", str(RUNNER), *args],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            for line in process.stdout:
                with self.lock:
                    self.lines = (self.lines + [line.strip()])[-12:]
            code = process.wait()
        except Exception as error:
            code = 1
            with self.lock:
                self.lines.append(str(error))
        with self.lock:
            self.exit_code = code
            self.running = False

    def status(self):
        with self.lock:
            return {"running": self.running, "exit_code": self.exit_code, "lines": list(self.lines)}


job = Job()


def schedule_status():
    with schedule_lock:
        if not SCHEDULE_CONFIG.exists():
            return {"schedule_active": False, "schedule_time": None}
        saved = json.loads(SCHEDULE_CONFIG.read_text(encoding="utf-8"))
        return {"schedule_active": True, "schedule_time": saved["time"]}


def run_scheduled_if_due(now=None):
    now = now or datetime.now()
    with schedule_lock:
        if not SCHEDULE_CONFIG.exists():
            return False
        saved = json.loads(SCHEDULE_CONFIG.read_text(encoding="utf-8"))
        if saved["time"] != now.strftime("%H:%M") or saved.get("last_run") == now.date().isoformat():
            return False
        if not job.start(["--recent"]):
            return False
        saved["last_run"] = now.date().isoformat()
        SCHEDULE_CONFIG.write_text(json.dumps(saved), encoding="utf-8")
        return True


def schedule_loop():
    while True:
        run_scheduled_if_due()
        threading.Event().wait(15)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def json_response(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlsplit(self.path).path == "/api/status":
            self.json_response(200, {**job.status(), **schedule_status(), "local_server": True})
        else:
            super().do_GET()

    def do_POST(self):
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            self.json_response(403, {"error": "Origem nao autorizada."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.json_response(415, {"error": "Envie JSON."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 2048:
                raise ValueError("Mensagem muito grande ou vazia.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("O corpo deve ser um objeto JSON.")
            route = urlsplit(self.path).path
            if route == "/api/update":
                if payload.get("mode") == "since":
                    since = date.fromisoformat(payload["since"])
                    if since > date.today():
                        raise ValueError("A data nao pode estar no futuro.")
                    args = ["--since", since.isoformat()]
                elif payload.get("mode") == "target":
                    count = int(payload["target"])
                    if not 1 <= count <= 10000:
                        raise ValueError("Use um total entre 1 e 10.000.")
                    args = ["--target", str(count)]
                else:
                    raise ValueError("Criterio invalido.")
                if not job.start(args):
                    self.json_response(409, {"error": "Ja existe uma atualizacao em andamento."})
                else:
                    self.json_response(202, job.status())
            elif route == "/api/schedule":
                if payload.get("active") is True:
                    hour = payload.get("time", "")
                    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hour):
                        raise ValueError("Horario invalido.")
                    with schedule_lock:
                        SCHEDULE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
                        SCHEDULE_CONFIG.write_text(json.dumps({"time": hour}), encoding="utf-8")
                elif payload.get("active") is False:
                    with schedule_lock:
                        SCHEDULE_CONFIG.unlink(missing_ok=True)
                else:
                    raise ValueError("Estado do agendamento invalido.")
                self.json_response(200, schedule_status())
            else:
                self.json_response(404, {"error": "Rota inexistente."})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.json_response(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    threading.Thread(target=schedule_loop, daemon=True).start()
    print(f"Pagina local: http://127.0.0.1:{args.port}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
