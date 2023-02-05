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
    def for_type_and_args(msg_type:str,args:dict):
        m=Message("")
        m.type=msg_type
        m.args=args
        return m

    def stringify(self) -> str:
        s=""
        for x in self.args:
            s+="%s=\"%s\""%(x,self.args[x])
        return "<%s %s/>"%(self.type.upper(),s)

    def __getitem__(self, item):
        return self.args[item]

    @staticmethod
    def parse_message(raw_string:str):
        raw_string=Message.strip_both(raw_string,"<","/>")
        sep=" "
        sep2="="
        messages=raw_string.split(sep)
        name=messages[0]
        args=dict()
        it=messages.__iter__()
        it.__next__()
        for x in it:
            if not x:
                continue

            s=x.split(sep2)
            assert len(s)==2

            key,value=s
            value=Message.strip_both(value,"\"","\"")
            args[key]=value
        return name.lower(),args

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
        return "Message{\n  type=\"%s\"\n  args=\"%s\"\n}"%(self.type.upper(),self.args)


class Player:
    def __init__(self,name,tid:str,sx:str,authenticated=False):
        self.disconnected=False
        self.authenticated=authenticated
        self.is_tournament=None
        self.is_anonymous=None
        self.is_regular=None
        self.name=name
        self.tid=tid
        self.sx=sx

    def is_ready(self):
        return self.authenticated and all((
            self.is_tournament is not None,
            self.is_regular is not None,
            self.is_anonymous is not None
        ))


class TenhouServerSocket:
    message_sep="\x00"

    def __init__(self, address):
        self.exit=False
        self.url=address[0]
        self.port=address[1]

        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.player=None

    def start(self):
        self.skt.bind((self.url,self.port))
        self.skt.listen(1)
        connection, client_address = self.skt.accept()
        while not self.exit:
            try:
                data=connection.recv(2048).decode("utf-8")
            except ConnectionError:
                if self.player is not None:
                    self.player.disconnected=True
                connection, client_address = self.skt.accept()
                self.send_reconnection_request()

                data=connection.recv(2048).decode("utf-8")
            messages=self.parse_messages(data)
            to_send=[]
            for x in messages:
                if x.type.lower()=="exit":
                    self.stop()
                    break
                msgs=self.process_message(connection,x)
                if isinstance(msgs,Message):
                    to_send.append(msgs)
                else:
                    to_send+=msgs
            self.send_messages(connection,to_send)
        connection.close()
        print(connection)

    def send_reconnection_request(self):
        pass

    @staticmethod
    def parse_messages(messages_str:str):
        t=TenhouServerSocket
        msgs=messages_str.split(t.message_sep)
        msgs=[x for x in msgs if x]
        return [Message(x) for x in msgs]

    def stop(self):
        self.exit=True
        self.skt.close()

    def process_message(self, conn:socket.socket, message:Message) -> Message | list[Message]:
        t=message.type.lower()
        print(message)
        if t=="helo":
            print("init player")
            name=message.args['name']
            tid=message.args['tid']
            sx=message.args['sx']
            return self.initialize_player(conn,name,tid,sx)

        elif t=='z': # keep alive
            return []

        elif t=='auth':
            print("authenticate")
            if self.player is None:
                self.send_error(conn,"not authenticated")
            token=message['val']
            return self.create_auth_message(token)

        elif t=='pxr':
            print("init game type")
            if self.player is None or not isinstance(self.player,Player):
                if not isinstance(self.player,Player):
                    self.player=None
                self.send_error(conn,"not authenticated")
                return []
            v=message['V']
            is_tournament=v=='-1'
            is_anonymous=v=='1'
            is_regular=v=='9'

            self.player.is_tournament=is_tournament
            self.player.is_anonymous=is_anonymous
            self.player.is_regular=is_regular
            return []
        elif t=="join":
            print(message)
            game_type=message['t']
            return self.join_game(game_type)

    def send_error(self, connection:socket.socket, message):
        m=Message.for_type_and_args("err",{
            "msg":message
        })
        self.send_messages(connection,m)

    def join_game(self, game_type):
        pass

    def send_messages(self, conn:socket.socket, messages:Message | list[Message]):
        if isinstance(messages,Message):
            messages=[messages]
        conn.sendall(self.message_sep.join(
            map(lambda x: (x.stringify()+self.message_sep),messages)
        ).encode())

    def initialize_player(self,conn:socket.socket,
                          name,tid,sx) -> Message:
        if self.player is not None:
            self.send_error(conn,"already authenticated")
        message=Message.for_type_and_args("hello",{
            "auth":"123abc",
            "PF4":"100", #rating
            "nintei":"101" #new level
        })
        self.player=Player(name=name,tid=tid,sx=sx)
        return message

    def create_auth_message(self, token:str):
        message = Message.for_type_and_args("LN", {
        })
        return message

if __name__ == '__main__':
    TenhouServerSocket(server_address).start()

