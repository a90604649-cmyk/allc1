import json
import queue
import secrets
import socket
import threading
import time
import tkinter as tk
from collections import deque

TCP_PORT = 43821
UDP_PORT = 43822
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
        return "red local"
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
        # J toggles the diagnostic terminal; typing J in the message box remains normal.
        root.bind_all("<KeyPress-j>", self.on_console_key)
        root.bind_all("<KeyPress-J>", self.on_console_key)

        self.events = queue.Queue()
        self.conn = None
        self.server = None
        self.discovery_receiver = None
        self.discovery_sender = None
        self.peer_id = secrets.token_hex(12)
        self.remote_id = None
        self.net_lock = threading.Lock()
        self.connecting_to = None
        self.connect_attempted_at = {}
        self.discovered_logged_at = {}
        self.discovered_last_seen = {}
        self.log_throttle = {}
        self.diag_lock = threading.Lock()
        self.diag_lines = deque(maxlen=160)
        self.console_visible = False
        self.closing = False
        self.mode = "searching"

        # Separate the UI and diagnostic console so the console survives screen changes.
        self.ui = tk.Frame(root, bg=BG)
        self.ui.pack(fill="both", expand=True)
        self.build_console()
        self.draw_searching()
        self.log("INFO", f"Dúo Chat iniciado; ID local {self.peer_id[:8]}")
        self.log("INFO", f"Descubrimiento automático por Wi-Fi (UDP {UDP_PORT}, TCP {TCP_PORT})")
        threading.Thread(target=self.server_worker, daemon=True).start()
        threading.Thread(target=self.discovery_worker, daemon=True).start()
        root.after(100, self.poll)

    def label(self, parent, text, size=11, color=FG, bold=False, **kw):
        return tk.Label(
            parent, text=text, bg=kw.pop("bg", parent.cget("bg")), fg=color,
            font=("Segoe UI", size, "bold" if bold else "normal"),
            justify=kw.pop("justify", "left"), **kw
        )

    def button(self, parent, text, command, primary=False):
        return tk.Button(
            parent, text=text, command=command,
            bg=ACCENT if primary else "#222936", fg=BG if primary else FG,
            activebackground="#8be6c8", relief="flat", bd=0,
            font=("Segoe UI", 10, "bold"), padx=14, pady=10, cursor="hand2"
        )

    def base(self, subtitle):
        for w in self.ui.winfo_children():
            w.destroy()
        head = tk.Frame(self.ui, bg=BG)
        head.pack(fill="x", padx=22, pady=(18, 9))
        self.label(head, "DÚO", 20, ACCENT, True).pack(anchor="w")
        if subtitle:
            self.label(head, subtitle, 9, MUTED).pack(anchor="w", pady=(2, 0))
        self.card = tk.Frame(self.ui, bg=PANEL)
        self.card.pack(fill="both", expand=True, padx=22, pady=(3, 18))

    def draw_searching(self):
        self.mode = "searching"
        self.base("")
        self.label(self.card, "Buscando otra PC…", 17, FG, True).place(relx=0.5, rely=0.5, anchor="center")

    def build_console(self):
        self.console_frame = tk.Frame(
            self.root, bg="#05070a", highlightbackground=ACCENT, highlightthickness=1
        )
        title = tk.Frame(self.console_frame, bg="#111720")
        title.pack(fill="x")
        tk.Label(
            title, text="DIAGNÓSTICO · J para ocultar", bg="#111720",
            fg=ACCENT, font=("Consolas", 9, "bold"), anchor="w"
        ).pack(fill="x", padx=8, pady=5)
        body = tk.Frame(self.console_frame, bg="#05070a")
        body.pack(fill="both", expand=True)
        self.console_text = tk.Text(
            body, bg="#05070a", fg="#c7d7e5", insertbackground=FG,
            font=("Consolas", 8), relief="flat", wrap="word",
            state="disabled", padx=7, pady=5
        )
        scrollbar = tk.Scrollbar(body, command=self.console_text.yview)
        self.console_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.console_text.pack(side="left", fill="both", expand=True)
        self.console_frame.place_forget()

    def on_console_key(self, event):
        # Do not steal the letter J while typing a message.
        try:
            if self.root.focus_get() is getattr(self, "entry", None):
                return None
        except tk.TclError:
            pass
        self.toggle_console()
        return "break"

    def toggle_console(self):
        self.console_visible = not self.console_visible
        if self.console_visible:
            self.console_frame.place(
                relx=1.0, rely=1.0, x=-10, y=-10,
                width=365, height=205, anchor="se"
            )
            self.console_frame.lift()
            self.render_console()
        else:
            self.console_frame.place_forget()

    def log(self, level, message, throttle_key=None, interval=0.0):
        now = time.monotonic()
        with self.diag_lock:
            if throttle_key:
                last = self.log_throttle.get(throttle_key, 0.0)
                if now - last < interval:
                    return
                self.log_throttle[throttle_key] = now
            stamp = time.strftime("%H:%M:%S")
            self.diag_lines.append(f"[{stamp}] [{level}] {message}")
        self.events.put(("diagnostic", None))

    def render_console(self):
        if not self.console_visible:
            return
        with self.diag_lock:
            lines = list(self.diag_lines)
        try:
            self.console_text.configure(state="normal")
            self.console_text.delete("1.0", "end")
            self.console_text.insert("end", "\\n".join(lines) + ("\\n" if lines else ""))
            self.console_text.configure(state="disabled")
            self.console_text.see("end")
        except tk.TclError:
            pass

    def server_worker(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", TCP_PORT))
            srv.listen(5)
            srv.settimeout(0.5)
            self.server = srv
            self.log("OK", f"Escuchando conexiones TCP en el puerto {TCP_PORT}")
            while not self.closing:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    addr = conn.getpeername()[0]
                except OSError:
                    addr = "IP desconocida"
                self.log("INFO", f"Conexión entrante desde {addr}")
                threading.Thread(target=self.handle_incoming, args=(conn,), daemon=True).start()
        except OSError as e:
            if not self.closing:
                self.log("ERROR", f"No se pudo abrir TCP {TCP_PORT}: {e}. Revisa el puerto y el firewall.")
        finally:
            try:
                srv.close()
            except OSError:
                pass

    def handle_incoming(self, conn):
        try:
            conn.settimeout(5)
            hello = read_packet(conn)
            remote_id = str(hello.get("id", ""))
            try:
                peer_ip = conn.getpeername()[0]
            except OSError:
                peer_ip = "IP desconocida"
            if hello.get("type") != "hello" or len(remote_id) != 24 or remote_id >= self.peer_id:
                self.log("WARN", f"Conexión entrante descartada desde {peer_ip}: identificador o emparejamiento no válido")
                conn.close()
                return
            self.log("INFO", f"PC detectada y negociación iniciada: {peer_ip}")
            with self.net_lock:
                if self.closing or self.conn is not None:
                    conn.close()
                    return
                self.conn = conn
                self.remote_id = remote_id
            send_packet(conn, {"type": "ready"})
            conn.settimeout(None)
            self.log("OK", f"Chat conectado con {peer_ip}")
            self.events.put(("connected", conn))
            threading.Thread(target=self.reader, args=(conn,), daemon=True).start()
        except Exception as e:
            if not self.closing:
                self.log("WARN", f"Falló la negociación entrante: {e}", throttle_key="incoming-handshake", interval=2.0)
            try:
                conn.close()
            except OSError:
                pass
            with self.net_lock:
                if self.conn is conn:
                    self.conn = None
                    self.remote_id = None

    def discovery_worker(self):
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            receiver.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            receiver.bind(("", UDP_PORT))
            receiver.settimeout(0.25)
            sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.discovery_receiver = receiver
            self.discovery_sender = sender
            self.log("OK", f"Escuchando descubrimiento automático por UDP {UDP_PORT}")
            next_beacon = 0.0
            next_search_notice = time.monotonic() + 10.0
            while not self.closing:
                with self.net_lock:
                    connected = self.conn is not None
                now = time.monotonic()
                if not connected and now >= next_search_notice:
                    recently_seen = any(now - t < 3.0 for t in self.discovered_last_seen.values())
                    if not recently_seen:
                        self.log(
                            "WARN",
                            "Todavía no detecto otra PC. Comprueba que ambas estén en la misma Wi-Fi, "
                            "que Windows permita Dúo Chat en redes privadas y que el router no aisle los dispositivos.",
                            throttle_key="no-peer-found", interval=9.0
                        )
                    next_search_notice = now + 10.0
                if not connected and now >= next_beacon:
                    beacon = json.dumps({
                        "type": "duo_discover",
                        "id": self.peer_id,
                        "port": TCP_PORT
                    }).encode("utf-8")
                    try:
                        sender.sendto(beacon, ("255.255.255.255", UDP_PORT))
                    except OSError as e:
                        self.log("ERROR", f"No se pudo anunciar la PC por Wi-Fi: {e}", throttle_key="broadcast-send", interval=5.0)
                    next_beacon = now + 0.8
                try:
                    data, addr = receiver.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                try:
                    packet = json.loads(data.decode("utf-8"))
                    remote_id = str(packet.get("id", ""))
                    port = int(packet.get("port", TCP_PORT))
                    if packet.get("type") != "duo_discover" or len(remote_id) != 24 or remote_id == self.peer_id:
                        continue
                    self.discovered_last_seen[remote_id] = now
                    last_logged = self.discovered_logged_at.get(remote_id, 0.0)
                    if now - last_logged >= 8.0:
                        self.log("INFO", f"PC detectada en la red: {addr[0]}")
                        self.discovered_logged_at[remote_id] = now
                    # Use deterministic peer-ID ordering: only the lower ID starts
                    # the TCP connection, preventing both PCs from connecting at once.
                    if self.peer_id < remote_id and 1 <= port <= 65535:
                        with self.net_lock:
                            if self.closing or self.conn is not None or self.connecting_to == remote_id:
                                continue
                            if now - self.connect_attempted_at.get(remote_id, 0.0) < 3.0:
                                continue
                            self.connect_attempted_at[remote_id] = now
                            self.connecting_to = remote_id
                        self.log("INFO", f"Intentando conectar con {addr[0]}:{port}")
                        threading.Thread(
                            target=self.connect_worker,
                            args=(addr[0], port, remote_id),
                            daemon=True
                        ).start()
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        except OSError as e:
            if not self.closing:
                self.log("ERROR", f"No se pudo iniciar el descubrimiento UDP {UDP_PORT}: {e}. Comprueba firewall, Wi-Fi y otras instancias.", throttle_key="discovery-init", interval=10.0)
        finally:
            for s in (receiver, sender):
                try:
                    s.close()
                except OSError:
                    pass

    def connect_worker(self, host, port, remote_id):
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            conn.settimeout(4)
            conn.connect((host, port))
            send_packet(conn, {"type": "hello", "id": self.peer_id})
            response = read_packet(conn)
            if response.get("type") != "ready":
                raise ConnectionError("La otra PC rechazó la conexión.")
            with self.net_lock:
                if self.closing or self.conn is not None:
                    conn.close()
                    return
                self.conn = conn
                self.remote_id = remote_id
            conn.settimeout(None)
            self.log("OK", f"Chat conectado con {host}")
            self.events.put(("connected", conn))
            threading.Thread(target=self.reader, args=(conn,), daemon=True).start()
        except Exception as e:
            if not self.closing:
                self.log("WARN", f"No se pudo conectar con {host}:{port}: {e}", throttle_key=f"connect-{remote_id}", interval=3.0)
            try:
                conn.close()
            except OSError:
                pass
        finally:
            with self.net_lock:
                if self.connecting_to == remote_id:
                    self.connecting_to = None

    def draw_chat(self):
        self.mode = "chat"
        self.base("Conectados · solo dos personas")
        self.chat = tk.Text(
            self.card, bg="#222936", fg=FG, insertbackground=FG,
            wrap="word", relief="flat", state="disabled", padx=12, pady=12
        )
        self.chat.pack(fill="both", expand=True, padx=15, pady=(15, 10))
        row = tk.Frame(self.card, bg=PANEL)
        row.pack(fill="x", padx=15, pady=(0, 15))
        self.entry = tk.Entry(row, bg="#222936", fg=FG, insertbackground=FG,
                              relief="flat", font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.send())
        self.button(row, "Enviar", self.send, True).pack(side="right")
        self.entry.focus_set()

    def write(self, who, msg):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{who}: {msg}\n\n")
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def send(self):
        if not self.conn or self.mode != "chat":
            return
        msg = self.entry.get().strip()[:3000]
        if not msg:
            return
        try:
            send_packet(self.conn, {"type": "message", "text": msg})
            self.write("Tú", msg)
            self.entry.delete(0, "end")
        except OSError:
            self.close()

    def reader(self, conn):
        try:
            while True:
                packet = read_packet(conn)
                if packet.get("type") == "message":
                    self.events.put(("message", str(packet.get("text", ""))[:3000]))
                elif packet.get("type") == "close":
                    self.events.put(("peer_close", None))
                    return
        except Exception:
            self.events.put(("peer_close", None))

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if self.closing:
                    continue
                if kind == "connected":
                    self.draw_chat()
                elif kind == "message" and self.mode == "chat":
                    self.write("Otra persona", value)
                elif kind == "peer_close":
                    self.finish_from_peer()
                    return
                elif kind == "network_error":
                    self.log("ERROR", value)
                elif kind == "diagnostic":
                    self.render_console()
                elif kind == "status":
                    pass
        except queue.Empty:
            pass
        if not self.closing:
            try:
                self.root.after(100, self.poll)
            except tk.TclError:
                pass

    def finish_from_peer(self):
        self.log("INFO", "La otra PC cerró la aplicación; cerrando esta ventana")
        self.closing = True
        self.cleanup_sockets(notify=False)
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def cleanup_sockets(self, notify):
        conn = self.conn
        self.conn = None
        if conn:
            if notify:
                try:
                    send_packet(conn, {"type": "close"})
                except OSError:
                    pass
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                conn.close()
            except OSError:
                pass
        for s in (self.server, self.discovery_receiver, self.discovery_sender):
            if s:
                try:
                    s.close()
                except OSError:
                    pass

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.cleanup_sockets(notify=True)
        try:
            self.root.destroy()
        except tk.TclError:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    DuoChat(root)
    root.mainloop()
