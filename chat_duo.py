import json
import queue
import secrets
import socket
import threading
import time
import tkinter as tk

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
        root.bind_all("<Escape>", lambda e: self.close())
        root.bind_all("<Control-q>", lambda e: self.close())

        self.events = queue.Queue()
        self.conn = None
        self.server = None
        self.discovery_receiver = None
        self.discovery_sender = None
        self.peer_id = secrets.token_hex(12)
        self.remote_id = None
        self.net_lock = threading.Lock()
        self.connecting_to = None
        self.closing = False
        self.mode = "searching"

        self.draw_searching()
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
        for w in self.root.winfo_children():
            w.destroy()
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=25, pady=(22, 12))
        self.label(head, "DÚO", 23, ACCENT, True).pack(anchor="w")
        self.label(head, subtitle, 10, MUTED).pack(anchor="w", pady=(3, 0))
        self.card = tk.Frame(self.root, bg=PANEL)
        self.card.pack(fill="both", expand=True, padx=25, pady=(4, 24))

    def draw_searching(self):
        self.mode = "searching"
        self.base("Chat privado · conexión automática")
        self.label(self.card, "Buscando la otra PC…", 17, FG, True).pack(anchor="w", padx=20, pady=(28, 9))
        self.label(
            self.card,
            "Abre Dúo Chat en la otra computadora conectada al mismo Wi-Fi. "
            "Cuando ambas estén abiertas, se conectarán solas.",
            11, MUTED, wraplength=430, justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 20))
        self.label(self.card, "No necesitas crear una sala ni escribir códigos.", 10, ACCENT).pack(anchor="w", padx=20, pady=(0, 10))
        self.label(
            self.card,
            "Mantén esta ventana abierta. Si Windows muestra una alerta de firewall, "
            "permite la conexión en redes privadas. La red debe permitir que los equipos se comuniquen entre sí.",
            9, MUTED, wraplength=430, justify="left"
        ).pack(anchor="w", padx=20, pady=(10, 18))
        self.button(self.card, "Cerrar", self.close).pack(anchor="w", padx=20, pady=(8, 20))

    def server_worker(self):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", TCP_PORT))
            srv.listen(5)
            srv.settimeout(0.5)
            self.server = srv
            self.events.put(("status", "listening"))
            while not self.closing:
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self.handle_incoming, args=(conn,), daemon=True).start()
        except OSError as e:
            if not self.closing:
                self.events.put(("network_error", "No se pudo abrir el puerto de chat. Cierra otra instancia de Dúo Chat y vuelve a abrirlo. " + str(e)))
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
            if hello.get("type") != "hello" or len(remote_id) != 24 or remote_id >= self.peer_id:
                conn.close()
                return
            with self.net_lock:
                if self.closing or self.conn is not None:
                    conn.close()
                    return
                self.conn = conn
                self.remote_id = remote_id
            send_packet(conn, {"type": "ready"})
            conn.settimeout(None)
            self.events.put(("connected", conn))
            threading.Thread(target=self.reader, args=(conn,), daemon=True).start()
        except Exception:
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
            next_beacon = 0.0
            while not self.closing:
                with self.net_lock:
                    connected = self.conn is not None
                now = time.monotonic()
                if not connected and now >= next_beacon:
                    beacon = json.dumps({
                        "type": "duo_discover",
                        "id": self.peer_id,
                        "port": TCP_PORT
                    }).encode("utf-8")
                    try:
                        sender.sendto(beacon, ("255.255.255.255", UDP_PORT))
                    except OSError:
                        pass
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
                    # Use deterministic peer-ID ordering: only the lower ID starts
                    # the TCP connection, preventing both PCs from connecting at once.
                    if self.peer_id < remote_id and 1 <= port <= 65535:
                        with self.net_lock:
                            if self.closing or self.conn is not None or self.connecting_to == remote_id:
                                continue
                            self.connecting_to = remote_id
                        threading.Thread(
                            target=self.connect_worker,
                            args=(addr[0], port, remote_id),
                            daemon=True
                        ).start()
                except (ValueError, TypeError, json.JSONDecodeError):
                    continue
        except OSError as e:
            if not self.closing:
                self.events.put(("network_error", "No se pudo activar el descubrimiento automático. Comprueba la red y el firewall. " + str(e)))
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
            self.events.put(("connected", conn))
            threading.Thread(target=self.reader, args=(conn,), daemon=True).start()
        except Exception:
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
        self.write("Sistema", "Conexión establecida. El historial no se guarda.")
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
                    if self.mode == "searching":
                        self.label(
                            self.card, value, 9, "#f08c8c",
                            wraplength=430, justify="left"
                        ).pack(anchor="w", padx=20, pady=(0, 8))
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
