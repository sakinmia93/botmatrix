"""Tiny local SMTP server for tests: every received mail is appended (JSON line) to a file. Usage: smtp_sink.py PORT FILE"""
import json, re, socketserver, sys
PORT, OUT = int(sys.argv[1]), sys.argv[2]

class H(socketserver.StreamRequestHandler):
    def handle(self):
        w = lambda s: (self.wfile.write((s + "\r\n").encode()), self.wfile.flush())
        w("220 sink"); data = False; buf = []; to = ""
        for raw in self.rfile:
            line = raw.decode(errors="ignore").rstrip("\r\n")
            if data:
                if line == ".":
                    body = "\n".join(buf)
                    m = re.search(r"Your code: (\d{6})", body)
                    open(OUT, "a").write(json.dumps({"to": to, "code": m.group(1) if m else "", "body": body}) + "\n")
                    data = False; buf = []; w("250 ok")
                else: buf.append(line)
                continue
            u = line.upper()
            if u.startswith("RCPT TO"): to = re.sub(r"[<>]", "", line.split(":", 1)[1]).strip().lower(); w("250 ok")
            elif u.startswith("EHLO"): w("250-sink"); w("250 AUTH PLAIN LOGIN")
            elif u.startswith("AUTH PLAIN"): w("235 ok")
            elif u.startswith("AUTH LOGIN"): w("334 VXNlcm5hbWU6"); self.rfile.readline(); w("334 UGFzc3dvcmQ6"); self.rfile.readline(); w("235 ok")
            elif u.startswith("DATA"): w("354 go"); data = True
            elif u.startswith("QUIT"): w("221 bye"); return
            else: w("250 ok")

class S(socketserver.ThreadingTCPServer): allow_reuse_address = True
S(("127.0.0.1", PORT), H).serve_forever()
