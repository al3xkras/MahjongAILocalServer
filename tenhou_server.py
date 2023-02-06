import socket

server_address = ('localhost', 10001)
http_response = b"""HTTP/1.1 200 OK

Content-Type: text/html
<html>
<body>foo</body>
</html>
"""

class MahjongGame:
    def __init__(self, random_seed):
        self.seed=random_seed
        self.tiles=list(range(136))
        import random
        random.seed(self.seed)
        random.shuffle(self.tiles)

    def get_next_deck(self):
        deck,tiles=self.tiles[:14],self.tiles[14:]
        self.tiles=tiles
        return Hand(deck)

    def get_next_tile(self):
        return self.tiles.pop(0)

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
        raw_string=Message.strip_both(Message.strip_both(raw_string,"<",">"),"<","/")
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
            if len(s)!=2:
                return Message("")

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
    def __init__(self,name,tid:str,sx:str,authenticated=False,seat=None,initial_hand=None):
        self.dan=0
        self.disconnected=False
        self.authenticated=authenticated
        self.is_tournament=None
        self.is_anonymous=None
        self.is_regular=None
        self.game_accepted=False
        self.is_ready_to_play=False
        self.name=name
        self.tid=tid
        self.sx=sx
        self.seat=seat
        self.initial_hand=initial_hand

    def is_initialized(self):
        return self.authenticated and all((
            self.is_tournament is not None,
            self.is_regular is not None,
            self.is_anonymous is not None,
        ))

    def is_ready(self):
        return self.is_initialized() and self.game_accepted and self.is_ready_to_play

class GameInfo:
    def __init__(self,round_number,honba_sticks,
            reach_sticks,bonus_tile_indicator,
            dealer,scores):
        self.round_number,self.honba_sticks,self.reach_sticks,self.bonus_tile_indicator,self.dealer,self.scores=\
            round_number,honba_sticks,\
            reach_sticks,bonus_tile_indicator,\
            dealer,scores

    @staticmethod
    def random():
        oya=0
        ten=[
            "25000",
            "25000",
            "25000",
            "25000",
        ]
        round_number="0"
        honba_sticks="0"
        reach_sticks="0"
        bonus_tiles=[
            "1","5","17" # max length: 5
        ]
        return GameInfo(round_number=round_number,
            honba_sticks=honba_sticks,reach_sticks=reach_sticks,
            bonus_tile_indicator=bonus_tiles,dealer=oya,
            scores=ten)


class Hand:
    delim=","
    def __init__(self, tiles):
        self.tiles=tiles

    @staticmethod
    def random_hand() -> "Hand":
        return Hand([
            0,0,0,1,2,3,1,2,3,6,28,14,32,
        ])

    def stringify(self):
        return self.delim.join(map(str,self.tiles))

class TenhouServerSocket:
    message_sep="\x00"

    def __init__(self, address):
        self.exit=False
        self.url=address[0]
        self.port=address[1]

        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.player=None
        self.game=MahjongGame(129487923519)

        self.opponents=[
            Player(name="Player1",tid="1",sx="M",authenticated=True,initial_hand=self.game.get_next_deck()),
            Player(name="Player1",tid="2",sx="M",authenticated=True,initial_hand=self.game.get_next_deck()),
            Player(name="Player1",tid="3",sx="M",authenticated=True,initial_hand=self.game.get_next_deck())
        ]

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
            print("join game")
            game_type=message['t']
            return self.join_game(game_type)
        elif t=='gok':
            print("game accepted")
            self.player.game_accepted=True
            return []
        elif t=='nextready':
            print("player ready")
            self.player.is_ready_to_play=True
            m1=self.initialize_game(GameInfo.random())
            if self.player.seat==0:
                return [m1,self.next_tile_message()]
            else:
                self.get_opponent_by_seat(0).discard_tile(self)
            return m1
        elif t=='n': # call a win
            print("player called a win")
            return []
        elif t=='reach':
            print("player called riichi")
            return []
        elif t=='d': # discard a tile
            print("player discarded a tile (east)")
            messages=[]
            for op in self.opponents:
                tile_msg=self.discard_by_opponent(op)
                messages.append(tile_msg)
            return []
        elif t=='e':
            print("player discarded a tile (south)")
        elif t=='f':
            print("player discarded a tile (east)")
        elif t=='g':
            print("player discarded a tile (north)")
        return []

    def send_error(self, connection:socket.socket, message):
        m=Message.for_type_and_args("err",{
            "msg":message
        })
        self.send_messages(connection,m)

    def next_tile_message(self):
        t=self.next_tile()
        return Message.for_type_and_args("T%d"%t,{
        })

    def discard_by_opponent(self, op_id:int):
        opponent=self.opponents[op_id]
        message_type=self.discard_tile_msg_type_by_seat[opponent.seat]

    def next_tile(self):
        return self.game.get_next_tile()

    def initialize_game(self,game_info:GameInfo)->Message:
        some_nums=[1,2]
        seed=[game_info.round_number,game_info.honba_sticks,game_info.reach_sticks,
            ] + some_nums + game_info.bonus_tile_indicator
        return Message.for_type_and_args("init",{
            "seed":self.list_stringify(seed),
            "ten":self.list_stringify(game_info.scores),
            "oya":game_info.dealer,
            "hai":self.player.initial_hand.stringify()
        })

    @staticmethod
    def list_stringify(lst:list):
        return ",".join(map(str,lst))

    def join_game(self, game_type) -> Message|list[Message]:
        join_msg=Message.for_type_and_args("GO",{
            "type":game_type[0],
        })
        game_msg=Message.for_type_and_args("TAIKYOKU",{
            'oya':str(self.player.seat), # 0 - east 4 - north
            'log':"foo"
        })
        op_info=self.opponents_info_message(self.opponents)
        out = [join_msg,game_msg,op_info]
        if self.player.seat==0:
            out.append(self.next_tile_message())
        return out

    def opponents_info_message(self, opponents:list[Player]) -> Message:
        sep=","
        players=[self.player]+opponents
        return Message.for_type_and_args("UN",{
            "dan":sep.join(map(lambda x:str(x.dan),players)),
            "n0":players[0].name,
            "n1":players[1].name,
            "n2":players[2].name,
            "n3":players[3].name,
        })

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
            "PF4":"1", #rating
            "nintei":"1" #new level
        })
        self.player=Player(name=name,tid=tid,sx=sx,seat=0,initial_hand=self.game.get_next_deck())
        return message

    def create_auth_message(self, token:str):
        message = Message.for_type_and_args("LN", {
        })
        return message

if __name__ == '__main__':
    TenhouServerSocket(server_address).start()

