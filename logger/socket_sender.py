import socket
addr=("localhost",10001)
if __name__ == '__main__':
    skt=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    skt.connect(addr)
    while True:
        data=input("input data to send: ")
        if len(data)==0:
            break
        data+="\0"
        skt.sendall(data.encode())
    skt.shutdown(socket.SHUT_RDWR)
    skt.close()


