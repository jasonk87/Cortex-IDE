import socket
import threading

HOST = 'localhost'
PORT = 55555

clients = {}

def handle_client(conn, addr):
    print(f'New connection from {addr}')
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            for client in clients.values():
                client.send(data)
    except Exception as e:
        print(f'Error handling client {addr}: {str(e)}')
    finally:
        conn.close()
        del clients[addr]

def start_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f'Server listening on {HOST}:{PORT}')
    while True:
        conn, addr = server.accept()
        clients[addr] = conn
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

if __name__ == '__main__':
    start_server()