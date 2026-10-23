import json
import queue
import secrets
import socket
import threading
import tkinter as tk
from tkinter import messagebox

PORT = 43821
BG, PANEL, ACCENT, FG, MUTED = "#101319", "#191e27", "#71d5b3", "#f0f3f8", "#aab4c4"

def send_packet(sock, data):
    sock.sendall((json.dumps(data, ensure_ascii=False) + "\n").encode("utf-8"))

def read_packet(sock):
    buf = bytearray()
    while len(buf) < 10000:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("La otra persona se desconectó.")
        if b == b"\n":
            return json.loads(buf.decode("utf-8"))
        buf.extend(b)
    raise ValueError("Paquete demasiado largo.")

def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

class DuoChat:
    def __init__(self, root):
        self.root = root
        root.title("Dúo Chat")
        root.geometry("540x570")
        root.minsize(470, 480)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind_all("<Escape>", lambda e: self.close())
        root.bind_all("<Control-q>", lambda e: self.close())
        self.events = queue.Queue()
        self.conn = None
        self.server = None
        self.code = ""
        self.closing = False
        self.mode = "home"
        self.draw_home()
        root.after(100, self.poll)

    def label(self, parent, text, size=11, color=FG, bold=False, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", parent.cget("bg")), fg=color,
                        font=("Segoe UI", size, "bold" if bold else "normal"),
                        justify=kw.pop("justify", "left"), **kw)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command, bg=ACCENT if primary else "#222936",
                         fg=BG if primary else FG, activebackground="#8be6c8",
                         relief="flat", bd=0, font=("Segoe UI", 10, "bold"),
                         padx=14, pady=10, cursor="hand2")

    def base(self, subtitle):
        for w in self.root.winfo_children(): w.destroy()
        head = tk.Frame(self.root, bg=BG); head.pack(fill="x", padx=25, pady=(22, 12))
        self.label(head, "DÚO", 23, ACCENT, True).pack(anchor="w")
        self.label(head, subtitle, 10, MUTED).pack(anchor="w", pady=(3, 0))
        self.card = tk.Frame(self.root, bg=PANEL)
        self.card.pack(fill="both", expand=True, padx=25, pady=(4, 24))

    def draw_home(self):
        self.mode = "home"; self.base("Chat privado entre dos computadoras")
        self.label(self.card, "Hablen sin cuentas", 17, FG, True).pack(anchor="w", padx=20, pady=(22, 8))
        self.label(self.card, "Sin nombre, correo ni teléfono. Los mensajes no se guardan al cerrar.", 10, MUTED, wraplength=430).pack(anchor="w", padx=20, pady=(0, 20))
        self.button(self.card, "Crear conversación", self.host, True).pack(fill="x", padx=20, pady=6)
        self.button(self.card, "Unirme a una conversación", self.join).pack(fill="x", padx=20, pady=6)
        self.label(self.card, "Ambas PCs deben estar en la misma red Wi-Fi o LAN. La X, Esc o Ctrl+Q cierra la sesión en ambos equipos.", 9, MUTED, wraplength=430).pack(anchor="w", padx=20, pady=(25, 12))

    def host(self):
        self.mode = "hosting"
        self.code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(10))
        self.base("Esperando a la otra computadora")
        self.label(self.card, "Comparte la IP y el código con la otra persona.", 12).pack(anchor="w", padx=20, pady=(22, 12))
        self.label(self.card, "IP local", 10, MUTED, True).pack(anchor="w", padx=20)
        self.label(self.card, local_ip(), 17, FG, True).pack(anchor="w", padx=20, pady=(3, 12))
        self.label(self.card, "Código de unión", 10, MUTED, True).pack(anchor="w", padx=20)
        self.label(self.card, self.code, 20, ACCENT, True).pack(anchor="w", padx=20, pady=(3, 15))
        self.button(self.card, "Cancelar", self.close).pack(anchor="w", padx=20, pady=8)
        threading.Thread(target=self.host_worker, daemon=True).start()

    def host_worker(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", PORT)); srv.listen(1); srv.settimeout(0.5)
            self.server = srv
            while not self.closing:
                try: conn, _ = srv.accept()
                except socket.timeout: continue
                try:
                    conn.settimeout(15)
                    hello = read_packet(conn)
                    if hello.get("type") != "hello" or not secrets.compare_digest(str(hello.get("code","")).upper(), self.code):
                        send_packet(conn, {"type":"error","message":"Código incorrecto"})
                        conn.close(); continue
                    send_packet(conn, {"type":"ready"}); conn.settimeout(None)
                    self.events.put(("connected", conn)); return
                except Exception:
                    conn.close()
        except Exception as e:
            if not self.closing: self.events.put(("error", str(e)))
        finally:
            try: srv.close()
            except OSError: pass

    def join(self):
        self.mode = "join"; self.base("Unirse sin cuenta")
        self.label(self.card, "IP de la otra PC", 10, MUTED, True).pack(anchor="w", padx=20, pady=(20, 4))
        self.ip_entry = tk.Entry(self.card, font=("Segoe UI", 12)); self.ip_entry.pack(fill="x", padx=20, ipady=7)
        self.label(self.card, "Código de unión", 10, MUTED, True).pack(anchor="w", padx=20, pady=(12, 4))
        self.code_entry = tk.Entry(self.card, font=("Consolas", 13)); self.code_entry.pack(fill="x", padx=20, ipady=7)
        self.status = self.label(self.card, "", 9, "#f08c8c", wraplength=430); self.status.pack(anchor="w", padx=20, pady=8)
        self.button(self.card, "Conectar", self.connect, True).pack(fill="x", padx=20, pady=5)
        self.button(self.card, "Volver", self.draw_home).pack(fill="x", padx=20, pady=5)

    def connect(self):
        host, code = self.ip_entry.get().strip(), self.code_entry.get().strip().upper()
        if not host or not code:
            self.status.config(text="Escribe la IP y el código."); return
        self.status.config(text="Conectando...")
        threading.Thread(target=self.client_worker, args=(host, code), daemon=True).start()

    def client_worker(self, host, code):
        c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            c.settimeout(12); c.connect((host, PORT))
            send_packet(c, {"type":"hello", "code":code})
            reply = read_packet(c)
            if reply.get("type") != "ready": raise ConnectionError(reply.get("message", "No se pudo conectar"))
            c.settimeout(None); self.events.put(("connected", c))
        except Exception as e:
            c.close(); self.events.put(("error", str(e)))

    def draw_chat(self):
        self.mode = "chat"; self.base("Conectados · 2 personas")
        self.chat = tk.Text(self.card, bg="#222936", fg=FG, insertbackground=FG, wrap="word", relief="flat", state="disabled", padx=12, pady=12)
        self.chat.pack(fill="both", expand=True, padx=15, pady=(15, 10))
        row = tk.Frame(self.card, bg=PANEL); row.pack(fill="x", padx=15, pady=(0, 15))
        self.entry = tk.Entry(row, bg="#222936", fg=FG, insertbackground=FG, relief="flat", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.send())
        self.button(row, "Enviar", self.send, True).pack(side="right")
        self.write("Sistema", "Conectados. No se guarda el historial.")
        self.entry.focus_set()

    def write(self, who, msg):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{who}: {msg}\n\n")
        self.chat.configure(state="disabled"); self.chat.see("end")

    def send(self):
        if not self.conn or self.mode != "chat": return
        msg = self.entry.get().strip()[:3000]
        if not msg: return
        try:
            send_packet(self.conn, {"type":"message", "text":msg})
            self.write("Tú", msg); self.entry.delete(0, "end")
        except OSError:
            self.close()

    def reader(self, conn):
        try:
            while True:
                p = read_packet(conn)
                if p.get("type") == "message": self.events.put(("message", str(p.get("text",""))[:3000]))
                elif p.get("type") == "close": self.events.put(("peer_close", None)); return
        except Exception:
            self.events.put(("peer_close", None))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if self.closing: continue
                if kind == "connected":
                    self.conn = value; self.draw_chat()
                    threading.Thread(target=self.reader, args=(value,), daemon=True).start()
                elif kind == "message" and self.mode == "chat": self.write("Otra persona", value)
                elif kind == "peer_close":
                    self.closing = True
                    try: self.root.destroy()
                    except tk.TclError: pass
                elif kind == "error":
                    if self.mode == "join":
                        self.status.config(text="No se pudo conectar: " + value)
                    else: messagebox.showerror("Dúo Chat", "No se pudo crear la sala: " + value)
        except queue.Empty: pass
        if not self.closing:
            try: self.root.after(100, self.poll)
            except tk.TclError: pass

    def close(self):
        if self.closing: return
        self.closing = True
        if self.conn:
            try: send_packet(self.conn, {"type":"close"})
            except OSError: pass
            try: self.conn.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            try: self.conn.close()
            except OSError: pass
        if self.server:
            try: self.server.close()
            except OSError: pass
        try: self.root.destroy()
        except tk.TclError: pass

if __name__ == "__main__":
    root = tk.Tk()
    DuoChat(root)
    root.mainloop()
