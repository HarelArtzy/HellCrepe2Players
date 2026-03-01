"""
 Program: HTTP Server Shell
 Author: Harel Teva Artzy
 Description: A http protocol server shell for an existing site template,
              handles client requests from browser and infinite clients, one after the other.
"""


import socket
import os
from email.utils import formatdate
import logging


QUEUE_SIZE = 10
IP = '0.0.0.0'
PORT = 8080
SOCKET_TIMEOUT = 2

WEB_ROOT = "build/web"
DEFAULT_URL = "index.html"
UPLOAD_DIR = "upload"

STATUS_CODES = {
    "/400": {
        "status": "400 Bad Request",
        "headers": {},
        "body": True
    },
    "/404": {
        "status": "404 Not Found",
        "headers": {},
        "body": True
    },
    "/forbidden": {
        "status": "403 Forbidden",
        "headers": {},
        "body": True
    },
    "/forbidden/": {
        "status": "403 Forbidden",
        "headers": {},
        "body": True
    },
    "/moved": {
        "status": "302 Moved Temporarily",
        "headers": {"Location": "/"},
        "body": False
    },
    "/moved/": {
        "status": "302 Moved Temporarily",
        "headers": {"Location": "/"},
        "body": False
    },
    "/error": {
        "status": "500 Internal Server Error",
        "headers": {},
        "body": True
    },
    "/error/": {
        "status": "500 Internal Server Error",
        "headers": {},
        "body": True
    }
}

CONTENT_TYPES = {
    "html": "text/html;charset=utf-8",
    "jpg": "image/jpeg",
    "css": "text/css",
    "js": "text/javascript; charset=UTF-8",
    "txt": "text/plain",
    "ico": "image/x-icon",
    "gif": "image/jpeg",
    "png": "image/png"
}


def get_file_data(file_name: str):
    """
    Extracts data from a file
    :param file_name:
    :return:
    """
    try:
        with open(file_name, "rb") as f:
            return f.read()
    except OSError:
        logging.exception(f"Failed reading file: {file_name}")
        return None


def get_content_type(file_name: str) -> str:
    """
    Gets the content type from a file
    :param file_name:
    :return:
    """
    if "." in file_name:
        ext = file_name.rsplit(".", 1)[1].lower()
    else:
        ext = ""
    return CONTENT_TYPES.get(ext, "application/octet-stream")


def build_http_header(status_code, content_type=None, content_length=None, extra_headers=None):
    lines = [f"HTTP/1.1 {status_code}"]
    if content_type is not None:
        lines.append(f"Content-Type: {content_type}")
    if content_length is not None:
        lines.append(f"Content-Length: {content_length}")
    if extra_headers:
        for k, v in extra_headers.items():
            lines.append(f"{k}: {v}")
    lines.append("Date: " + formatdate(timeval=None, localtime=False, usegmt=True))
    lines.append("Connection: close")
    return "\r\n".join(lines) + "\r\n\r\n"


def send_simple_text(client_socket, status, text: str):
    """
    Sends a text message
    :param client_socket:
    :param status:
    :param text:
    :return:
    """
    body = text.encode("utf-8")
    header_ = build_http_header(status, "text/plain; charset=utf-8", len(body))
    client_socket.sendall(header_.encode() + body)


def send_bytes(client_socket, status, data: bytes, content_type: str):
    """
    Sends data to client
    :param client_socket:
    :param status:
    :param data:
    :param content_type:
    :return:
    """
    header_ = build_http_header(status, content_type, len(data))
    client_socket.sendall(header_.encode() + data)


def parse_query_string(qs: str) -> dict:
    """
    Extracts parameters from a query string and returns them as a dict.
    """
    params = {}
    if not qs:
        return params
    for pair in qs.split("&"):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        params[k] = v
    return params


def safe_basename(name: str) -> str:
    """
    Converts a name to a safe base name.
    :param name:
    :return:
    """
    return os.path.basename(name).strip()


def handle_client_request(resource: str, method: str, body_bytes: bytes, client_socket: socket.socket) -> None:
    """
    Handles all client requests
    :param resource:
    :param method:
    :param body_bytes:
    :param client_socket:
    :return:
    """
    logging.info(f"Request: {method} {resource}")

    if resource in STATUS_CODES:
        route = STATUS_CODES[resource]
        status = route["status"]
        extra_headers = route["headers"]
        has_body = route["body"]
        body = (b"<html><body><h1>" + status.encode() + b"</h1></body></html>") if has_body else b""
        header_ = build_http_header(status, "text/html;charset=utf-8", len(body), extra_headers)
        client_socket.sendall(header_.encode() + body)
        return

    if "?" in resource:
        path, qs = resource.split("?", 1)
    else:
        path, qs = resource, ""

    if path == "/calculate-next":
        if method != "GET":
            handle_client_request("/400", "GET", b"", client_socket)
            return
        params = parse_query_string(qs)
        if "num" not in params:
            handle_client_request("/400", "GET", b"", client_socket)
            return
        try:
            n = int(params["num"])
        except ValueError:
            handle_client_request("/400", "GET", b"", client_socket)
            return
        send_simple_text(client_socket, "200 OK", str(n + 1))
        return

    # if path == "/calculate-area":
    #     if method != "GET":
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #     params = parse_query_string(qs)
    #     if "height" not in params or "width" not in params:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #     try:
    #         h = float(params["height"])
    #         w = float(params["width"])
    #     except ValueError:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #     area = (h * w) / 2.0
    #     send_simple_text(client_socket, "200 OK", str(area))
    #     return
    #
    # if path == "/upload":
    #     if method != "POST":
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #     params = parse_query_string(qs)
    #     if "file-name" not in params:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #
    #     os.makedirs(UPLOAD_DIR, exist_ok=True)
    #     filename = safe_basename(params["file-name"])
    #     if not filename:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #
    #     if not body_bytes:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #
    #     out_path = os.path.join(UPLOAD_DIR, filename)
    #     try:
    #         with open(out_path, "wb") as f:
    #             f.write(body_bytes)
    #     except OSError:
    #         handle_client_request("/error", "GET", b"", client_socket)
    #         return
    #
    #     send_simple_text(client_socket, "200 OK", "OK")
    #     return
    #
    # if path == "/image":
    #     if method != "GET":
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #     params = parse_query_string(qs)
    #     if "image-name" not in params:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #
    #     filename = safe_basename(params["image-name"])
    #     if not filename:
    #         handle_client_request("/400", "GET", b"", client_socket)
    #         return
    #
    #     full_path = os.path.join(UPLOAD_DIR, filename)
    #     if not os.path.isfile(full_path):
    #         handle_client_request("/404", "GET", b"", client_socket)
    #         return
    #
    #     data = get_file_data(full_path)
    #     if data is None:
    #         handle_client_request("/error", "GET", b"", client_socket)
    #         return
    #
    #     send_bytes(client_socket, "200 OK", data, get_content_type(full_path))
    #     return
    #
    # if method != "GET":
    #     handle_client_request("/400", "GET", b"", client_socket)
    #     return

    if path == "/" or path == "":
        relative_path = DEFAULT_URL
    else:
        relative_path = path.lstrip("/")

    full_path = os.path.join(WEB_ROOT, relative_path)
    logging.info(f"Static path: {full_path}")

    if not os.path.isfile(full_path):
        handle_client_request("/404", "GET", b"", client_socket)
        return

    data = get_file_data(full_path)
    if data is None:
        handle_client_request("/error", "GET", b"", client_socket)
        return

    send_bytes(client_socket, "200 OK", data, get_content_type(full_path))


def validate_http_request(request: str):
    """
    Checks if http request is valid.
    :param request:
    :return:
    """
    if not request:
        return False, "", "", {}

    if "\r\n\r\n" not in request:
        return False, "", "", {}

    head, _ = request.split("\r\n\r\n", 1)
    lines = head.split("\r\n")
    request_line = lines[0]

    parts = request_line.split(" ")
    if len(parts) != 3:
        return False, "", "", {}
    method, uri, version = parts

    if method not in ("GET", "POST"):
        return False, "", "", {}
    if version != "HTTP/1.1":
        return False, "", "", {}

    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    return True, uri, method, headers


def recv_full_request(client_socket: socket.socket) -> tuple[str, bytes]:
    """
    Read until \r\n\r\n then read body by Content-Length (if exists).
    Returns (request_text, body_bytes).
    """
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = client_socket.recv(4096)
        if not chunk:
            break
        data += chunk

    if b"\r\n\r\n" not in data:
        return "", b""

    head, rest = data.split(b"\r\n\r\n", 1)
    request_text = head.decode("iso-8859-1") + "\r\n\r\n"

    headers_lines = head.decode("iso-8859-1").split("\r\n")[1:]
    content_length = 0
    for line in headers_lines:
        if ":" in line:
            k, v = line.split(":", 1)
            if k.strip().lower() == "content-length":
                try:
                    content_length = int(v.strip())
                except ValueError:
                    content_length = 0

    body = rest
    while len(body) < content_length:
        chunk = client_socket.recv(4096)
        if not chunk:
            break
        body += chunk

    return request_text + rest[:0].decode("iso-8859-1", errors="ignore"), body[:content_length]


def handle_client(client_socket):
    """
    Handles each client individually.
    :param client_socket:
    :return:
    """
    try:
        request_text, body_bytes = recv_full_request(client_socket)
        if not request_text:
            return

        valid_http, resource, method, headers = validate_http_request(request_text)
        if valid_http:
            handle_client_request(resource, method, body_bytes, client_socket)
        else:
            handle_client_request("/400", "GET", b"", client_socket)
    except Exception as e:
        logging.exception(f"Error: {e}")
        try:
            handle_client_request("/error", "GET", b"", client_socket)
        except Exception as e:
            logging.exception(f"Error: {e}")

def main():
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server_socket.bind((IP, PORT))
        server_socket.listen(QUEUE_SIZE)
        logging.info(f"Listening for connections on port {PORT}")
        print(f"Listening for connections on port {PORT}\n")

        while True:
            client_socket, client_address = server_socket.accept()
            try:
                logging.info(f"New connection received from {client_address[0]}:{client_address[1]}")
                client_socket.settimeout(SOCKET_TIMEOUT)
                handle_client(client_socket)
            finally:
                client_socket.close()
    finally:
        server_socket.close()



if __name__ == "__main__":
    logging.basicConfig(
        filename='server.log',
        level=logging.INFO,
        filemode="w",
        format="%(asctime)s %(levelname)s %(message)s"
    )

    assert "html" in CONTENT_TYPES
    assert CONTENT_TYPES.get("jpg") == "image/jpeg"
    assert CONTENT_TYPES.get("png") == "image/png"
    assert get_content_type("a.html") == CONTENT_TYPES["html"]
    assert get_content_type("a.JPG") == CONTENT_TYPES["jpg"]
    assert get_content_type("a.css") == "text/css"
    assert get_content_type("a.js") == "text/javascript; charset=UTF-8"
    assert get_content_type("a.txt") == "text/plain"
    assert get_content_type("a.ico") == "image/x-icon"
    assert get_content_type("a.gif") == "image/jpeg"
    assert get_content_type("a.png") == "image/png"

    header = build_http_header("200 OK", "text/html", 10)
    assert header.startswith("HTTP/1.1 ")
    assert header.endswith("\r\n\r\n")
    assert "Content-Length: 10" in header
    assert "Content-Type: text/html" in header

    assert validate_http_request("GET / HTTP/1.1\r\n\r\n")[0] is True
    assert validate_http_request("GETT / HTTP/1.1\r\n\r\n")[0] is False

    print("All asserts passed")


    main()