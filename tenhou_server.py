import socket

server_address = ('localhost', 10001)
http_response = b"""HTTP/1.1 200 OK

Content-Type: text/html
<html>
<body>foo</body>
</html>
"""

class Message:
    def __init__(self, raw_string:str):
        self.type,self.args=self.parse_message(raw_string)

    @staticmethod
    def parse_message(raw_string:str):
        raw_string=Message.strip_both(raw_string,"<",">")
        sep=" "
        sep2="="
        messages=raw_string.split(sep)
        name=messages[0]
        args=dict()
        it=messages.__iter__()
        it.__next__()
        for x in it:
            key,value=x.split(sep2)
            value=Message.strip_both(value,"\"","\"")
            args[key]=value
        return name,args

    @staticmethod
    def strip_both(string:str, left_sym:str, right_sym:str):
        i0=0
        i1=len(string)
        if string.startswith(left_sym):
            i0=len(left_sym)
        if string.endswith(right_sym):
            i1-=len(right_sym)
        return string[i0:i1]

    def __str__(self):
        return "Message{\n  type=\"%s\"\n  args=\"%s\"\n}"%(self.type,self.args)


class TenhouServerSocket:
    message_sep="\x00"

    def __init__(self, address):
        self.exit=False
        self.url=address[0]
        self.port=address[1]

        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self):
        self.skt.bind((self.url,self.port))
        self.skt.listen(1)
        connection, client_address = self.skt.accept()
        while not self.exit:
            try:
                data=connection.recv(2048).decode("utf-8")
            except ConnectionError:
                connection, client_address = self.skt.accept()
                data=connection.recv(2048).decode("utf-8")
            messages=self.parse_messages(data)
            for x in messages:
                print(x)
                if x.type.lower()=="exit":
                    break
            connection.send(http_response)

        connection.close()

        print(connection)

    @staticmethod
    def parse_messages(messages_str:str):
        t=TenhouServerSocket
        msgs=messages_str.split(t.message_sep)
        msgs=[x for x in msgs if x]
        return [Message(x) for x in msgs]




    def stop(self):
        self.exit=True
        self.skt.close()

if __name__ == '__main__':
    TenhouServerSocket(server_address).start()

