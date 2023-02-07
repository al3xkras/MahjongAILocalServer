import socket
import time
import random
from collections import deque
from client.mahjong_tile import Tile
from agents.utils.win_calc import WinCalc

server_address = ('localhost', 10001)

class MahjongGame:
    def __init__(self, game_info:"GameInfo", random_seed=None):
        print("mahjong game: init")
        self.seed=random_seed
        self.tiles=list(range(136))
        self.seats=deque(range(4))
        self.game_info=game_info
        if self.seed is not None:
            random.seed(self.seed)
        else:
            random.seed()
        random.shuffle(self.tiles)
        self.seats.rotate(random.randint(0,3))
        self.last_drawn_tile=None
        print(self)

    def __str__(self):
        return "MahjongGame{" \
               "%s\n  ,%s\n  ,%s\n  ," \
               "}"%(self.game_info,self.tiles,self.seats)

    def get_next_hand(self):
        return Hand([self.get_next_tile() for _ in range(13)])

    def get_next_tile(self):
        tile=self.tiles.pop(0)
        self.last_drawn_tile=tile
        return tile

    def get_last_drawn_tile(self):
        return self.last_drawn_tile

    def get_next_player_seat(self):
        print("seats left: ",self.seats)
        assert len(self.seats)>0
        return self.seats.pop()

    def restart(self,game_info,random_seed):
        self.__init__(game_info,random_seed)

    def next_round(self):
        self.game_info.next_round(
            bonus_tiles=[27],
            scores=[20000,23000,25000,25000],
            dealer_seat=random.randint(0,3)
        )
        self.__init__(self.game_info,self.seed)

    def end_round(self):
        self.tiles=[]

    def is_round_over(self):
        return len(self.tiles)==0

    def is_game_over(self):
        return self.is_round_over() and self.game_info.is_last_round()

    @staticmethod
    def tile_from_136_to_34(tile:int):
        return tile//4

class Message:
    def __init__(self, raw_string:str):
        self.type,self.args=self.parse_message(raw_string)

    @staticmethod
    def for_type_and_args(msg_type:str,args=None):
        m=Message("")
        m.type=msg_type
        m.args=args if args is not None else dict()
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
        self.name=name
        self.tid=tid
        self.sx=sx
        self.seat=seat
        self.hand=initial_hand
        self.discarded_tiles=[]

    def is_initialized(self):
        return self.authenticated and all((
            self.is_tournament is not None,
            self.is_regular is not None,
            self.is_anonymous is not None,
        ))

    def discard_random(self,tile_drawn:int):
        tiles=self.hand.tiles
        i=random.randint(0,len(tiles)-1)
        d=tiles[i]
        tiles[i]=tile_drawn
        self.discarded_tiles.append(d)
        return d

    def get_last_discarded_tile(self):
        return self.discarded_tiles[len(self.discarded_tiles)-1]

    def discard(self, tile_number:int, tile_drawn:int):
        tiles=self.get_hand().get_tiles()
        i = tiles.index(tile_number)
        tile = tiles[i]
        tiles[i]=tile_drawn
        self.discarded_tiles.append(tile)
        return tile

    def get_hand(self) -> "Hand":
        if self.hand is None:
            raise Exception("player hand is not initialized")
        return self.hand

    def can_call_kan(self, tile:int):
        return self.hand.get_tiles().count(tile)>=3

    def can_call_chii(self, seat:int, tile:int):
        if (seat + 1) % 4 != self.seat:
            return False
        f = MahjongGame.tile_from_136_to_34
        tile=f(tile)
        if tile>26:
            return False
        mapped=list(map(f,self.hand.get_tiles()))
        t0,t1,t2,t3=[False]*4
        if tile>=2:
            t0=mapped.count(tile - 2) >= 1
        if tile >= 1:
            t1 = mapped.count(tile - 1) >= 1
        if tile <= 26:
            t2 = mapped.count(tile + 1) >= 1
        if tile <= 25:
            t3 = mapped.count(tile + 2) >= 1
        return t0 and t1 or t1 and t2 or t2 and t3

    def can_call_pon(self,tile:int):
        return self.hand.get_tiles().count(tile)>=2

    def can_call_win(self, tile:int):
        return self.hand.is_waiting() and self.hand.can_call_win(self.discarded_tiles,tile)


    def call_kan(self, tile_called:int, tile_drawn:int, tile_discarded:int):
        pass

    def call_chii(self, tile_called:int, tile_discarded:int):
        pass

    def call_pon(self, tile_called:int, tile_discarded:int):
        pass

    def next_round(self,hand:"Hand",seat:int):
        self.hand=hand
        self.seat=seat

class GameInfo:
    def __init__(self, round_number:int, honba_sticks:int,
                 reach_sticks:int, bonus_tiles:list[int],
                 dealer_seat:int, scores:list[int]):
        self.round_number=round_number
        self.honba_sticks=honba_sticks
        self.reach_sticks=reach_sticks
        self.bonus_tiles=bonus_tiles
        self.dealer_seat=dealer_seat
        self.scores=scores
        self.max_rounds=8

    def __str__(self) -> str:
        return "GameInfo{" \
               "%s\n    ,%s\n    ,%s\n    ,%s\n    ,%s\n    ,%s\n    ,%s\n    " \
               "}"%(self.round_number,self.honba_sticks,self.reach_sticks,self.bonus_tiles,
                    self.dealer_seat,self.scores,self.max_rounds)

    @staticmethod
    def initial():
        oya=random.randint(0,3)
        ten=[
            25000,25000,25000,25000
        ]
        round_number=0
        honba_sticks=0
        reach_sticks=0
        bonus_tiles=[
            27 # max length: 5
        ]
        return GameInfo(round_number=round_number,
                honba_sticks=honba_sticks, reach_sticks=reach_sticks,
                bonus_tiles=bonus_tiles, dealer_seat=oya,
                scores=ten)

    def open_next_bonus_tile(self, tile:int):
        self.bonus_tiles.append(tile)

    def set_scores(self,scores:list[int]):
        self.scores=scores

    def set_dealer(self, dealer_seat):
        self.dealer_seat=dealer_seat

    def get_dealer(self):
        return self.dealer_seat

    def next_round(self,scores,dealer_seat,bonus_tiles):
        assert self.round_number<self.max_rounds
        self.round_number+=1
        self.set_scores(scores)
        self.dealer_seat=dealer_seat
        self.set_bonus_tiles(bonus_tiles)

    def is_last_round(self):
        return self.round_number>=self.max_rounds

    def set_bonus_tiles(self,bonus_tiles:list[int]):
        self.bonus_tiles=bonus_tiles


class Hand:
    delim=","
    def __init__(self, tiles:list[int]):
        self.tiles=tiles

    def stringify(self):
        return self.delim.join(map(str,self.tiles))

    def get_tiles(self,fmt=136) -> list[int]:
        if fmt==34:
            return list(map(MahjongGame.tile_from_136_to_34, self.tiles))
        return self.tiles

    def is_waiting(self) -> bool:
        pass

    def can_call_win(self, discarded_tiles:list[int], tile:int, is_riichi:bool) -> bool:
        pass

    def is_furiten(self,discarded_tiles:list[int],tile:int):
        f=MahjongGame.tile_from_136_to_34
        return f(tile) in map(f,discarded_tiles)

class TenhouServerSocket:
    message_sep="\x00"
    tile_msg_type_by_seat={
        0:"d",1:"e",
        2:"f",3:"g"
    }

    def __init__(self, address):
        self.exit=False
        self.url=address[0]
        self.port=address[1]

        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.player=Player("","","",False)
        self.game_info=GameInfo.initial()
        self.game=MahjongGame(self.game_info)

        self.opponents=[
            Player(seat=1, name="Player1",
                   tid="1", sx="M", authenticated=True),
            Player(seat=2, name="Player2",
                   tid="2", sx="M", authenticated=True),
            Player(seat=3, name="Player3",
                   tid="3", sx="M", authenticated=True)
        ]

        self.last_discarded_tile=None
        self.last_discarded_tile_seat=None

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
        #print(message)
        messages = []

        if self.is_game_over():
            print("GAME OVER")
            messages.append(self.game_over_message())
            return messages
        elif self.is_round_over():
            print("ROUND OVER")
            self.next_round()
            messages.append(self.round_over_message())
            return messages
        if t=="helo":
            print("init player")
            name=message.args['name']
            tid=message.args['tid']
            sx=message.args['sx']
            messages+=[self.initialize_player(conn,name,tid,sx)]
        elif t=='z': # keep alive
            pass
        elif t=='auth':
            print("authenticate")
            if self.player is None:
                self.send_error(conn,"not authenticated")
            token=message['val']
            messages+=[self.create_auth_message(token)]

        elif t=='pxr':
            print("init game type")
            if self.player is None or not isinstance(self.player,Player):
                if not isinstance(self.player,Player):
                    self.player=None
                self.send_error(conn,"not authenticated")
                return messages
            v=message['V']
            is_tournament=v=='-1'
            is_anonymous=v=='1'
            is_regular=v=='9'

            self.player.is_tournament=is_tournament
            self.player.is_anonymous=is_anonymous
            self.player.is_regular=is_regular
            messages+=[]

        elif t=="join":
            print("join game")
            game_type=message['t']
            messages+=self.join_game(game_type)

        elif t=='gok':
            print("game accepted")
            self.player.game_accepted=True
            messages+=[]

        elif t=='nextready':
            print("player ready")
            self.next_round()
            #self.player.seat=
            #self.player.hand=self.game.get_next_deck()

            init_msg=self.initialize_game(self.game_info)
            self.send_messages(conn,init_msg)
            i=self.game.game_info.dealer_seat
            while i!=self.player.seat:
                if self.is_game_over() or self.is_round_over():
                    break
                else:
                    messages.append(self.draw_tile_by_player_message(i,""))
                    if self.is_game_over() or self.is_round_over():
                        break
                    messages.append(self.discard_by_player(i, None))
                i=(i+1)%4
            if not self.is_game_over() and not self.is_round_over():
                messages.append(self.draw_tile_by_player_message(self.player.seat, self.game.get_next_tile()))
            #self.send_messages(conn,self.call_chii_by_player(self.opponents[2].seat,self.opponents[1].seat, 1*4,2*4,3*4))
            #self._wait_for_a_while()
            #self.send_messages(conn,self.call_pon_by_player(self.opponents[0].seat,self.opponents[2].seat,0))
            #self._wait_for_a_while()
            #self.send_messages(conn,self.call_kan_by_player(self.opponents[1].seat, self.opponents[2].seat, 5))
            #messages.append(
            #    self.call_kan_by_player(self.player.seat, self.opponents[2].seat, 1))

        elif t=='reach':
            print("player called riichi")
            tile=int(message['hai'])
            messages+=[]
        elif t=='d':
            print("player discarded a tile")
            tile=int(message['p'])
            messages+=self.next_turn(conn)
        elif t=='n':
            print("player called a meld")
            print(message)
            meld_type=int(message.args.get('type',0))
            print("meld type:",meld_type)
            #types:
            # 0 - cancel meld
            # 1 - call pon
            # 2 - call an open kan
            # 3 - call chii
            # 4 - call a kan
            # 5 - call a chankan
            # 6 - claim victory
            # 7,9 - win check after drawing
            if meld_type==0: # meld cancelled
                print("meld cancelled")

            elif meld_type==1:
                print("player called a pon")

                tile1 = int(message['hai0'])
                #tile2=tile1 if not "hai1" in message else int(message["hai0"])
                pon_msg=self.call_pon_by_player(self.player,tile1,
                                                self.last_discarded_tile_seat)
                messages.append(pon_msg)

            elif meld_type==5 or meld_type==2 or meld_type==4:
                print("player called a kan")
                tile_called = int(message.args.get('hai', -1))
                print("tile called (kan):",tile_called)
                msgs=[]
                if tile_called==self.game.get_last_drawn_tile():
                    #closed kan
                    from_seat=self.player.seat
                else:
                    #open kan
                    from_seat=self.last_discarded_tile_seat
                msgs.append(self.call_kan_by_player(self.player.seat,from_seat,tile=tile_called))
                #draw next tile after calling a kan
                msgs.append(self.draw_tile_by_player_message(self.player.seat,self.game.get_next_tile()))
                self.send_messages(conn,msgs)

            elif meld_type==3:
                tile0=int(message['hai0'])
                tile1=int(message['hai1'])
                msgs=[]
                from_seat=(self.player.seat+3)%4
                msgs.append(self.call_chii_by_player(self.player.seat,from_seat,
                     self.get_player_by_seat(from_seat).get_last_discarded_tile(),tile0,tile1,0))
                self.send_messages(conn,msgs)

            elif meld_type==6:
                print("Player called a win!")
                self.game.end_round()
                self.send_messages(conn,self.round_over_message_winner(self.player.seat,
                            self.player.seat,0,self.player.hand.get_tiles(),[25,25,25,25]))
                time.sleep(5)
                self.send_messages(conn, self.initialize_game(self.game_info))
                self.next_round()
                time.sleep(4)

        return messages

    def next_turn(self,conn:socket.socket) -> list[Message]:
        def send(message):
            self.send_messages(conn,message)
            self._wait_for_a_while()
        for _ in range(self.player.seat+1,self.player.seat+4):
            i = _%4
            if self.is_game_over() or self.is_round_over():
                break
            elif i!=self.player.seat:
                send(self.draw_tile_by_player_message(i,""))
                if self.is_game_over() or self.is_round_over():
                    break
                send(self.discard_by_player(i, None))

        if not self.is_game_over() and not self.is_round_over():
            send(self.draw_tile_by_player_message(self.player.seat,self.game.get_next_tile()))
        return []

    def call_meld_by_player(self) -> Message:
        return Message.for_type_and_args("N",args={
            "who":"foo"
        })

    def reveal_bonus_indicator(self, tile:int) -> Message:
        return Message.for_type_and_args("dora",args={
            "hai":str(tile)
        })

    def call_riichi_by_opponent(self, opponent_seat:int):
        return Message.for_type_and_args("reach",args={
            "step":"1",
            "who":"bar",
        })

    def is_game_over(self):
        return self.game.is_game_over()

    def is_round_over(self):
        return self.game.is_round_over()

    def game_over_message(self):
        return Message.for_type_and_args("owari")

    def round_over_message_winner(self, winner_seat:int, win_from:int, win_tile:int, hand_tiles:list[int], win_scores:list[int]):
        return Message.for_type_and_args("agari",{
            "who":self.seat_to_player_number(winner_seat),
            "fromWho":self.seat_to_player_number(win_from),
            "machi":win_tile,
            "hai":self.list_stringify(hand_tiles),
            "ten":self.list_stringify(win_scores)
        })

    def next_round(self):
        if self.game.is_round_over():
            print("game: round over")
            self.game.next_round()
        else:
            self.game.restart(self.game_info,None)
        players=[self.get_player_by_seat(i) for i in range(4)]
        for p in players:
            p.seat=self.game.get_next_player_seat()
            p.hand=self.game.get_next_hand()

    def round_over_message(self) -> Message:
        args=dict()
        for i in range(4):
            args["hai%d"%i]=self.get_player_by_seat(i).get_hand().stringify()
        return Message.for_type_and_args("RYUUKYOKU",args)

    def send_error(self, connection:socket.socket, message):
        m=Message.for_type_and_args("err",{
            "msg":message
        })
        self.send_messages(connection,m)

    def get_player_by_seat(self,seat_num):
        if self.player.seat==seat_num:
            return self.player
        return [x for x in self.opponents if x.seat==seat_num][0]

    def discarded_tile_message(self, seat:int, tile:int) -> Message:
        seat_str=self.discarded_tile_message_type_by_seat(seat)
        args=dict()

        tiles34=self.player.hand.get_tiles(fmt=34)
        print("Seat %s discarded: %s"%(seat_str,Tile.tile136_to_string([tile])))
        if WinCalc.is_fulfilled(tiles34,tile//4):
            args['t']="9"
        elif self.player.can_call_kan(tile):
            args['t']="3"
        elif self.player.can_call_pon(tile) or self.player.can_call_chii(seat,tile):
            args['t']="1"
        return Message.for_type_and_args("%s%d"%(seat_str,tile),args)

    def _wait_for_a_while(self):
        time.sleep(1.5)

    def discarded_tile_message_type_by_seat(self, seat:int):
        lst=['d','e','f','g']
        return lst[(seat-self.player.seat)%4]

    def discarded_tile_seat_by_message_type(self, msg_type: str):
        lst = ['d', 'e', 'f', 'g']
        assert msg_type in lst
        return (self.player.seat+lst.index(msg_type))%4

    def drawn_tile_message_type_by_seat(self, seat:int):
        lst=['t','u','v','w']
        return lst[(seat-self.player.seat)%4]

    def drawn_tile_seat_by_message_type(self, msg_type: str):
        lst=['t','u','v','w']
        assert msg_type in lst
        return (self.player.seat+lst.index(msg_type))%4

    def draw_tile_by_player_message(self, seat:int, tile:int|str) -> Message:
        t=self.drawn_tile_message_type_by_seat(seat)
        return Message.for_type_and_args("%s%s"%(t,tile))

    def discard_by_player(self, seat, tile_number:int|None) -> Message:
        player=self.get_player_by_seat(seat)
        tile_drawn=self.game.get_next_tile()
        if tile_number is None:
            tile = player.discard_random(tile_drawn)
        else:
            tile = player.discard(tile_number,tile_drawn)
        self.last_discarded_tile=tile
        self.last_discarded_tile_seat=seat
        return self.discarded_tile_message(seat, tile)

    def seat_to_player_number(self, seat:int):
        return (seat-self.player.seat)%4

    def call_pon_by_player(self, seat:int, from_seat:int, tile:int, chankan=False) -> Message:
        pon_tiles=[MahjongGame.tile_from_136_to_34(tile)]*3
        t=1 if chankan else 0
        called_index=0
        return Message.for_type_and_args("n", {
            "who": str(self.seat_to_player_number(seat)),
            "from_who": str(self.seat_to_player_number(from_seat)),
            "type":"pon",
            "m": "%d %d %s %s %s"%(t,called_index,pon_tiles[0],pon_tiles[1],pon_tiles[2]),
        })

    def call_chii_by_player(self, seat:int, from_seat:int, tile1: int, tile2: int, tile3:int, tile_called_num=0) -> Message:
        return Message.for_type_and_args("n", {
            "who": str(self.seat_to_player_number(seat)),
            "from_who": str(self.seat_to_player_number(from_seat)),
            "type":"chi",
            "m": "%d %s %s %s"%(tile_called_num,tile1,tile2,tile3),
        })

    def call_kan_by_player(self, seat: int, from_seat:int, tile: int) -> Message:
        tiles = [MahjongGame.tile_from_136_to_34(tile)] * 4
        called_index = 0
        return Message.for_type_and_args("n", {
            "who": str(self.seat_to_player_number(seat)),
            "from_who": str(self.seat_to_player_number(from_seat)),
            "type": "kan",
            "m": " %d %s %s %s %s" % (called_index, tiles[0], tiles[1], tiles[2],tiles[3]),
        })

    def initialize_game(self,game_info:GameInfo)->Message:
        some_nums=[1,2]
        seed=[game_info.round_number,game_info.honba_sticks,game_info.reach_sticks,
            ] + some_nums + game_info.bonus_tiles
        return Message.for_type_and_args("init",{
            "seed":self.list_stringify(seed),
            "ten":self.list_stringify(game_info.scores),
            "oya":game_info.dealer_seat,
            "hai":self.player.hand.stringify()
        })

    @staticmethod
    def list_stringify(lst:list):
        return ",".join(map(str,lst))

    def join_game(self, game_type) -> list[Message]:
        join_msg=Message.for_type_and_args("GO",{
            "type":game_type[0],
        })
        game_msg=Message.for_type_and_args("TAIKYOKU",{
            'oya':str(self.player.seat), # 0 - east 4 - north
            'log':"foo"
        })
        op_info=self.opponents_info_message(self.opponents)
        out = [join_msg,game_msg,op_info]
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
        if self.player is not None and self.player.is_initialized():
            self.send_error(conn,"already authenticated")
        elif self.player is not None:
            self.player=None
        message=Message.for_type_and_args("hello",{
            "auth":"123abc",
            "PF4":"1", #rating
            "nintei":"1" #new level
        })
        if self.player is None or not self.player.is_initialized():
            print("player init")
            self.player=Player(seat=0,name=name, tid=tid,sx=sx)
        return message

    def create_auth_message(self, token:str):
        message = Message.for_type_and_args("LN", {
        })
        return message

if __name__ == '__main__':
    TenhouServerSocket(server_address).start()
