import random
import socket
import threading
import time
import traceback
from collections import deque

from agents.utils.win_calc import WinCalc
from client.mahjong_tile import Tile

server_address = ('localhost', 10001)

class Tiles:
    t136=dict((x, Tile.t136_to_g([x])) for x in range(136))
    t34=dict((x, Tile.t34_to_g([x])) for x in range(34))
    t34inv = dict((Tile.t34_to_g([x]),x) for x in range(34))

    @classmethod
    def t136_to_g(cls,tile136:int) -> str:
        return cls.t136[tile136]

    @classmethod
    def t136_to_34(cls, tile136: int) -> int:
        return cls.t34inv[cls.t136[tile136]]

    @classmethod
    def g_to_t34(cls, g:str) -> int:
        return cls.t34inv[g]

    @classmethod
    def t34_to_136(cls, tile34:int) -> list[int]:
        return [tile34*4+i for i in range(4)]


class MahjongGame:
    def __init__(self, game_info: "GameInfo", random_seed=None):
        print("mahjong game: init")
        self.seed = random_seed
        self.tiles = list(range(136))
        self.seats = deque(range(4))
        self.game_info = game_info
        if self.seed is not None:
            random.seed(self.seed)
        else:
            random.seed()
        random.shuffle(self.tiles)
        self.seats.rotate(random.randint(0, 3))
        self.last_drawn_tile = None
        self.winner_seat=None
        print(self)

    def __str__(self):
        return "MahjongGame{" \
               "%s\n  ,%s\n  ,%s\n  ," \
               "}" % (self.game_info, self.tiles, self.seats)

    def get_next_hand(self):
        return Hand([self.get_next_tile() for _ in range(13)])

    def get_next_tile(self):
        tile = self.tiles.pop(0)
        self.last_drawn_tile = tile
        return tile

    def get_last_drawn_tile(self):
        return self.last_drawn_tile

    def get_next_player_seat(self):
        print("seats left: ", self.seats)
        assert len(self.seats) > 0
        return self.seats.pop()

    def set_winner_seat(self, winner:int):
        self.winner_seat=winner

    def get_winner_seat(self):
        return self.winner_seat

    def restart(self, game_info, random_seed):
        self.__init__(game_info, random_seed)

    def next_round(self):
        self.game_info.next_round(
            bonus_tiles=[27],
            scores=[20000, 23000, 25000, 25000],
            dealer_seat=random.randint(0, 3)
        )
        self.__init__(self.game_info, self.seed)

    def end_round(self,winner=None):
        if winner is None:
            self.tiles = []
        else:
            self.winner_seat=winner

    def is_round_over(self):
        return len(self.tiles) == 0 or self.winner_seat is not None

    def is_game_over(self):
        return self.is_round_over() and self.game_info.is_last_round()



class Message:
    def __init__(self, raw_string: str):
        self.type, self.args = self.parse_message(raw_string)
        self.round_number=None
        self.timeout=0

    @staticmethod
    def for_type_and_args(msg_type: str, args=None):
        m = Message("")
        m.type = msg_type
        m.args = args if args is not None else dict()
        return m

    def stringify(self) -> str:
        s = ""
        for x in self.args:
            s += "%s=\"%s\"" % (x, self.args[x])
        return "<%s %s/>" % (self.type.upper(), s)

    def __getitem__(self, item):
        return self.args[item]

    @staticmethod
    def parse_message(raw_string: str):
        raw_string = Message.strip_both(Message.strip_both(raw_string, "<", ">"), "<", "/")
        sep = " "
        sep2 = "="
        messages = raw_string.split(sep)
        name = messages[0]
        args = dict()
        it = messages.__iter__()
        it.__next__()
        for x in it:
            if not x:
                continue

            s = x.split(sep2)
            if len(s) != 2:
                return Message("")

            key, value = s
            value = Message.strip_both(value, "\"", "\"")
            args[key] = value
        return name.lower(), args

    @staticmethod
    def strip_both(string: str, left_sym: str, right_sym: str):
        i0 = 0
        i1 = len(string)
        if string.startswith(left_sym):
            i0 = len(left_sym)
        if string.endswith(right_sym):
            i1 -= len(right_sym)
        return string[i0:i1]

    def __str__(self):
        return "Message{\n  type=\"%s\"\n  args=\"%s\"\n}" % (self.type.upper(), self.args)


class Player:
    def __init__(self, name, tid: str, sx: str, authenticated=False, seat=None, initial_hand=None):
        self.dan = 0
        self.disconnected = False
        self.authenticated = authenticated
        self.is_tournament = None
        self.is_anonymous = None
        self.is_regular = None
        self.name = name
        self.tid = tid
        self.sx = sx
        self.seat = seat
        self.hand = initial_hand
        self.discarded_tiles = []
        self.last_drawn_tile = None
        self.table_tiles = []
        self.is_riichi = False

    def is_initialized(self):
        return self.authenticated and all((
            self.is_tournament is not None,
            self.is_regular is not None,
            self.is_anonymous is not None,
        ))

    def discard_random(self):
        hand = self.get_hand()
        i = random.randint(0, len(hand.tiles) - 1)
        d = hand[i]
        assert self.get_last_drawn_tile() is not None
        hand[i] = self.get_last_drawn_tile()
        self.last_drawn_tile = None
        self.discarded_tiles.append(d)
        return d

    def get_last_discarded_tile(self):
        return self.discarded_tiles[len(self.discarded_tiles) - 1]

    def draw_tile(self, tile136: int):
        self.last_drawn_tile = tile136

    def get_last_drawn_tile(self):
        return self.last_drawn_tile

    def set_riichi(self, status:bool):
        self.is_riichi=status

    def discard(self, tile136: int):
        if tile136 in self.discarded_tiles:
            return tile136

        f=lambda t:Tiles.t136_to_34(t)
        if self.get_last_drawn_tile() is None:
            print("last drawn tile is None")
        elif f(tile136)==f(self.get_last_drawn_tile()):
            print("equal to last drawn tile")
            self.discarded_tiles.append(self.last_drawn_tile)
            l=self.last_drawn_tile
            self.last_drawn_tile=None
            return l
        hand = self.get_hand()
        i=0
        for x in hand.tiles:
            if f(x)==f(tile136):
                break
            i+=1
        if i==len(hand.tiles):
            raise Exception("no such tile")
        tile = hand[i]

        if self.get_last_drawn_tile() is None:
            hand.tiles.pop(i)
        else:
            hand[i] = self.get_last_drawn_tile()

        self.last_drawn_tile = None
        self.discarded_tiles.append(tile)
        return tile

    def get_hand(self) -> "Hand":
        if self.hand is None:
            raise Exception("player hand is not initialized")
        return self.hand

    def can_call_kan(self, tile136: int):
        f = lambda t: Tiles.t136_to_g(t)
        return list(map(f,self.hand.tiles)).count(f(tile136)) >= 3

    def can_call_chii(self, seat: int, tile136: int):
        if (self.seat - 1) % 4 != seat:
            return False
        f = lambda t: Tiles.t136_to_g(t)
        tile = f(tile136)
        if ord(tile) > ord("🀡") or ord(tile)<ord("🀙"):
            return False
        tiles = sorted(list(map(f, self.hand.tiles)))
        print("chii tiles",tiles)
        print("tile to chii",tile)
        t0, t1, t2, t3 = [False] * 4
        if tile >= "🀛":
            t0 = tiles.count(chr(ord(tile)-2)) >= 1
        if tile >= "🀚":
            t1 = tiles.count(chr(ord(tile)-1)) >= 1
        if tile <= "🀗":
            t2 = tiles.count(chr(ord(tile)+1)) >= 1
        if tile <= "🀘":
            t3 = tiles.count(chr(ord(tile)+2)) >= 1
        return (t0 and t1) or \
               (t1 and t2) or \
               (t2 and t3)

    def can_call_pon(self, tile136: int):
        f = lambda t: Tiles.t136_to_g(t)
        return list(map(f,self.hand.tiles)).count(f(tile136)) >= 2

    def next_round(self, hand: "Hand", seat: int):
        self.hand = hand
        self.seat = seat

    def call_meld(self, tile136:int, hand_tiles136:list[int]):
        if self.last_drawn_tile is not None and self.last_drawn_tile in hand_tiles136:
            hand_tiles136.remove(self.last_drawn_tile)
            self.last_drawn_tile=None

        hand_tiles_upd=list()
        print(hand_tiles136)
        print(tile136)
        tiles=[tile136]
        for x in self.hand.tiles:
            f=lambda _:_
            if len(hand_tiles136)==0:
                hand_tiles_upd.append(x)
            elif f(x)==f(hand_tiles136[0]):
                tiles.append(hand_tiles136.pop(0))
            else:
                hand_tiles_upd.append(x)
        self.hand.tiles=hand_tiles_upd
        self.table_tiles.append(tile136)
        self.table_tiles+=hand_tiles136
        return tiles

    def call_pon(self, tile136:int):
        f = lambda t: Tiles.t136_to_g(t)
        hand_tiles=list()
        for x in self.hand.tiles:
            if len(hand_tiles)>=2:
                break
            if f(tile136)==f(x):
                hand_tiles.append(x)
        if len(hand_tiles)<2:
            print("not possible to call pon.")
            print(Tiles.t136_to_g(tile136))
            print("player tiles",Tiles.t136_to_g(self.hand.tiles))
            raise Exception
        return self.call_meld(tile136,hand_tiles)

    def call_kan(self, tile136:int):
        f = Tiles.t136_to_34
        hand_tiles=list()
        for x in self.hand.tiles:
            if len(hand_tiles)>=3:
                break
            if f(tile136)==f(x):
                hand_tiles.append(x)
        if len(hand_tiles)<3:
            raise Exception("unable to call kan")
        return self.call_meld(tile136,hand_tiles)

class GameInfo:
    def __init__(self, round_number: int, honba_sticks: int,
                 reach_sticks: int, bonus_tiles: list[int],
                 dealer_seat: int, scores: list[int]):
        self.round_number = round_number
        self.honba_sticks = honba_sticks
        self.reach_sticks = reach_sticks
        self.bonus_tiles = bonus_tiles
        self.dealer_seat = dealer_seat
        self.active_seat = dealer_seat
        self.scores = scores
        self.max_rounds = 8

    def __str__(self) -> str:
        return "GameInfo{" \
               "%s\n    ,%s\n    ,%s\n    ,%s\n    ,%s\n    ,%s\n    ,%s\n    " \
               "}" % (self.round_number, self.honba_sticks, self.reach_sticks, self.bonus_tiles,
                      self.dealer_seat, self.scores, self.max_rounds)

    @staticmethod
    def initial():
        oya = random.randint(0, 3)
        ten = [
            25000, 25000, 25000, 25000
        ]
        round_number = 0
        honba_sticks = 0
        reach_sticks = 0
        bonus_tiles = [
            27  # max length: 5
        ]
        return GameInfo(round_number=round_number,
                        honba_sticks=honba_sticks, reach_sticks=reach_sticks,
                        bonus_tiles=bonus_tiles, dealer_seat=oya,
                        scores=ten)

    def open_next_bonus_tile(self, tile: int):
        self.bonus_tiles.append(tile)

    def set_scores(self, scores: list[int]):
        self.scores = scores

    def set_dealer(self, dealer_seat):
        self.dealer_seat = dealer_seat

    def get_dealer(self):
        return self.dealer_seat

    def next_round(self, scores, dealer_seat, bonus_tiles):
        assert self.round_number < self.max_rounds
        self.round_number += 1
        self.set_scores(scores)
        self.dealer_seat = dealer_seat
        self.set_bonus_tiles(bonus_tiles)

    def is_last_round(self):
        return self.round_number >= self.max_rounds

    def set_bonus_tiles(self, bonus_tiles: list[int]):
        self.bonus_tiles = bonus_tiles


class Hand:
    delim = ","

    def __init__(self, tiles: list[int]):
        self.tiles = tiles

    def stringify(self):
        return self.delim.join(map(str, self.tiles))

    def get_tiles(self) -> list[int]:
        return self.tiles

    def __setitem__(self, i:int, tile136:int):
        self.tiles[i]=tile136

    def __getitem__(self, i:int):
        return self.tiles[i]

class TenhouServerSocket:
    message_sep = "\x00"
    tile_msg_type_by_seat = {
        0: "d", 1: "e",
        2: "f", 3: "g"
    }

    def __init__(self, address):
        self.exit = False
        self.url = address[0]
        self.port = address[1]

        self.skt = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        self.player = Player("", "", "", False)

        self.game_info = GameInfo.initial()
        self.game = MahjongGame(self.game_info,random_seed=761761)

        self.meld_event=threading.Event()
        self.meld_type=None

        self.message_exchange_lock=threading.Lock()
        self.message_exchanger=dict()

        # 3498274 nothing special
        # 209014207127490 ok
        # 991030420223 ok
        # -5920003992219882329 ok
        # 761761 ron is called
        # 1234567 - no ready hand collected
        # -9999999 - ron is called
        # 1 - ron is called
        # 16778 - ron is called
        # 54981297492777
        self.opponents = [
            Player(seat=1, name="Player1",tid="1", sx="M", authenticated=True),
            Player(seat=2, name="Player2",tid="2", sx="M", authenticated=True),
            Player(seat=3, name="Player3",tid="3", sx="M", authenticated=True)
        ]

        self.last_discarded_tile = None
        self.last_discarded_tile_seat = None

    def start(self):
        self.skt.bind((self.url, self.port))
        self.skt.listen(1)
        connection, client_address = self.skt.accept()
        while not self.exit:
            try:
                data = connection.recv(2048).decode("utf-8")
            except ConnectionError:
                connection, client_address = self.skt.accept()

                data = connection.recv(2048).decode("utf-8")
            messages = self.parse_messages(data)
            to_send = []
            for x in messages:
                xtype=x.type.lower()
                if xtype == "exit":
                    self.stop()
                    break
                if xtype in self.message_exchanger:
                    self.message_exchange_lock.acquire()
                    self.message_exchanger[xtype][1]=x
                    self.message_exchanger[xtype][0].notify()
                    self.message_exchange_lock.release()
                    continue
                msgs = self.process_message(connection, x)
                if isinstance(msgs, Message):
                    to_send.append(msgs)
                else:
                    to_send += msgs
            self.send_messages(connection, to_send)
        connection.close()
        print(connection)

    def parse_messages(self, messages_str: str):
        t = TenhouServerSocket
        msgs = messages_str.split(t.message_sep)
        msgs = [Message(x) for x in msgs if x]
        for x in msgs:
            x.round_number=self.game.game_info.round_number
        return msgs

    def stop(self):
        self.exit = True
        self.skt.close()

    def _handle_next_turn(self,conn:socket.socket)->bool:
        if self.meld_event.is_set():
            meld_answer = self.wait_for_meld_by_player(self.game.game_info.active_seat)
            if not meld_answer is None:
                game_over, msgs = self.handle_meld(meld_answer)
                self.meld_event.clear()
                self.send_messages(conn, msgs)
                if game_over:
                    return False
        can_continue, msgs = self.next_turn(conn)
        self.send_messages(conn, msgs)
        if not can_continue:
            return False
        return True

    def wait_for_meld_by_player(self,player_seat:int) -> Message | None:
        if player_seat == self.player.seat:
            return self.wait_for_message("n")
        print("Meld can be called by player %s"%player_seat)
        if self.meld_type is None:
            raise Exception("meld type is unexpectedly None")
        meld_type=self.meld_type
        self.meld_type=None
        if meld_type=="chi":
            print("player %s can call chi"%player_seat)
            tiles=input("input hand tiles to meld")

    def handle_next_turn(self,conn:socket.socket):
        val=None
        while self.game.game_info.active_seat != self.player.seat:
            val=self._handle_next_turn(conn)
            if not val:
                return
        if val is not None and not val:
            return
        self._handle_next_turn(conn)

    def process_message(self, conn: socket.socket, message: Message) -> Message | list[Message]:
        if message.round_number!=self.game.game_info.round_number:
            return []
        t = message.type.lower()
        # print(message)
        messages = []
        assert self.player==self.get_player_by_seat(self.player.seat)

        if self.is_game_over():
            print("GAME OVER")
            messages.append(self.game_over_message())
            return messages

        elif self.is_round_over() and self.game.get_winner_seat() is None:
            print("ROUND OVER")
            self.next_round()
            messages.append(self.round_over_message())
            return messages

        elif self.is_round_over() and self.game.get_winner_seat() is not None:
            print("ROUND OVER BY PLAYER %s"%self.game.get_winner_seat())
            self.next_round()
            messages.append(self.round_over_message_winner(
                self.player.seat,self.player.seat, 0,
                self.player.hand.get_tiles(), [25, 25, 25, 25]))
            return messages

        if t == "helo":
            print("init player")
            name = message.args['name']
            tid = message.args['tid']
            sx = message.args['sx']
            messages += [self.initialize_player(conn, name, tid, sx)]

        elif t == 'z':  # keep alive
            pass

        elif t == 'auth':
            print("authenticate")
            if self.player is None:
                self.send_error(conn, "not authenticated")
            token = message['val']
            messages += [self.create_auth_message(token)]

        elif t == 'pxr':
            print("init game type")
            if self.player is None or not isinstance(self.player, Player):
                if not isinstance(self.player, Player):
                    self.player = None
                self.send_error(conn, "not authenticated")
                return messages
            v = message['V']
            is_tournament = v == '-1'
            is_anonymous = v == '1'
            is_regular = v == '9'

            self.player.is_tournament = is_tournament
            self.player.is_anonymous = is_anonymous
            self.player.is_regular = is_regular
            messages += []

        elif t == "join":
            print("join game")
            game_type = message['t']
            messages += self.join_game(game_type)
            self.next_round()

        elif t == 'gok':
            print("game accepted")
            self.player.game_accepted = True
            messages += []

        elif t == 'nextready':
            print("player ready")
            init_msg = self.initialize_game(self.game_info)
            self.send_messages(conn, init_msg)
            time.sleep(3)
            self.handle_next_turn(conn)

        elif t == 'reach':
            tile136 = int(message['hai'])
            print("player called riichi after discarding %s"%Tiles.t136_to_g(tile136))
            self.player.set_riichi(True)

        elif t in ['d','e','f','g']:
            raise Exception("discards should be handled elsewhere")

        elif t == 'n':
            raise Exception("meld should be handled elsewhere")

        return messages

    def handle_meld(self,message:Message) -> list[bool,list[Message]]:
        """
        :return: is game over after a meld call (None if meld cannot be called)
        """
        if message.round_number!=self.game.game_info.round_number:
            return [True,[]]
        if self.is_round_over() or self.is_game_over():
            return [True,[]]
        messages=[]
        assert message.type.lower()=='n'
        meld_type = int(message.args.get('type', 0))
        print("meld type:", meld_type)
        # types:
        # 0 - cancel meld
        # 1 - call pon
        # 2 - call an open kan
        # 3 - call chii
        # 4 - call a kan
        # 5 - call a chankan
        # 6 - claim victory
        # 7,9 - win check after drawing
        if meld_type == 0:
            print("meld cancelled")
        elif meld_type == 1:
            print("player called a pon")

            tile136 = int(message['hai0'])
            print("pon tile:",Tiles.t136_to_g(tile136))
            pon_msg = self.call_pon_by_player(self.player.seat, self.last_discarded_tile_seat, self.last_discarded_tile)
            self.game.game_info.active_seat=self.player.seat
            messages.append(pon_msg)

        elif meld_type == 2 or meld_type == 4:
            print("player called a kan")
            tile_called = int(message.args.get('hai0', -1))
            print("tile called (kan):", tile_called)
            if tile_called == self.game.get_last_drawn_tile():
                # closed kan
                from_seat = self.player.seat
            else:
                # open kan
                from_seat = self.last_discarded_tile_seat
            self.game.game_info.active_seat = self.player.seat
            messages.append(self.call_kan_by_player(self.player.seat, from_seat,
                                                    tile136=self.last_discarded_tile))
            # draw next tile after calling a kan
            messages.append(self.draw_tile_by_player(self.player.seat, self.game.get_next_tile()))

        elif meld_type == 3:
            tile0 = int(message['hai0'])
            tile136 = int(message['hai1'])
            from_seat = (self.player.seat + 3) % 4
            messages.append(
                self.call_chii_by_player(self.player.seat, from_seat,
                    self.get_player_by_seat(from_seat).get_last_discarded_tile(),
                        tile0, tile136, 0))

        elif meld_type == 6:
            time.sleep(2)
            self.end_round(winner=self.player.seat)
            print("Player called a win!")
            return [True,messages]
        return [False,messages]

    def end_round(self,winner=None):
        self.game.end_round(winner=winner)

    def wait_for_message(self, msg_type:str, timeout=None)->Message:
        msg_type=msg_type.lower()
        if msg_type in self.message_exchanger:
            raise Exception("already waiting for this type of messages")
        print("waiting for a message of type: \"%s\""%msg_type)
        self.message_exchange_lock.acquire()
        c=threading.Condition()
        self.message_exchanger[msg_type]=[c,None]
        self.message_exchange_lock.release()
        c.acquire()
        c.wait(timeout)
        c.release()
        self.message_exchange_lock.acquire()
        message=self.message_exchanger[msg_type][1]
        del self.message_exchanger[msg_type]
        self.message_exchange_lock.release()
        return message

    def is_waiting_for_meld(self):
        return "n" in self.message_exchanger

    def next_turn(self,conn:socket.socket) -> list[bool,list[Message]]:
        """
        :return: can pass the turn to the next player
        """
        if self.is_round_over() or self.is_game_over():
            print("round/game is over")
            return [False,[]]

        if self.is_waiting_for_meld():
            print("a meld is active. waiting...")
            return [False,[]]

        print("player decks:")
        for i in range(4):
            s=",".join(sorted([Tiles.t136_to_g(x) for x in self.get_player_by_seat(i).get_hand().get_tiles()]))
            print("seat %d (self): "%i + s if i==self.player.seat else "seat %d: "%i + s)

        active_seat = self.game.game_info.active_seat
        print("active seat: %d"%active_seat)
        self.game_info.active_seat = (self.game.game_info.active_seat + 1) % 4

        self.send_messages(conn,self.draw_tile_by_player(active_seat, self.game.get_next_tile()))
        self.send_messages(conn,self.discard_tile_by_player(active_seat, self.wait_for_discard_msg(active_seat)))
        self.handle_next_turn(conn)
        return [True,[]]


    def wait_for_discard_msg(self, by_seat: int) -> int:
        """
        :return: discarded tile (0-135)
        """
        if by_seat!=self.player.seat:
            plr=self.get_player_by_seat(by_seat)
            tiles=plr.hand
            s=" ".join([str(x)+Tiles.t136_to_g(x) for x in tiles])
            print("player tiles: %s"%s)
            print("table tiles: %s"%plr.table_tiles)
            print("last drawn tile: %s"%plr.last_drawn_tile)
            i=input("which one to discard? (leave empty for random):")
            if not i:
                i=random.randint(0,len(plr.hand.get_tiles()))
                return plr.hand.get_tiles()[i]
            else:
                i=int(i)
                return i
        msg_type=self.discarded_tile_message_type_by_seat(by_seat)
        msg=self.wait_for_message(msg_type)
        return int(msg['t'])


    def call_meld_by_player(self) -> Message:
        return Message.for_type_and_args("N", args={
            "who": "foo"
        })

    def reveal_bonus_indicator(self, tile: int) -> Message:
        return Message.for_type_and_args("dora", args={
            "hai": str(tile)
        })

    def call_riichi_by_opponent(self, opponent_seat: int):
        return Message.for_type_and_args("reach", args={
            "step": "1",
            "who": "bar",
        })

    def is_game_over(self):
        return self.game.is_game_over()

    def is_round_over(self):
        return self.game.is_round_over()

    def game_over_message(self):
        return Message.for_type_and_args("owari")

    def round_over_message_winner(self, winner_seat: int, win_from: int, win_tile: int, hand_tiles: list[int],
                                  win_scores: list[int]):
        return Message.for_type_and_args("agari", {
            "who": self.seat_to_player_number(winner_seat),
            "fromWho": self.seat_to_player_number(win_from),
            "machi": win_tile,
            "hai": self.list_stringify(hand_tiles),
            "ten": self.list_stringify(win_scores)
        })

    def next_round(self):
        players = [self.player]+self.opponents
        if self.game.is_round_over():
            print("game: round over")
            self.game.next_round()
            assert not self.game.is_round_over()

            for p in players:
                p.seat = self.game.get_next_player_seat()
                p.hand = self.game.get_next_hand()
            print("players re-initialized")

        elif self.is_game_over():
            print("game over")
            self.stop()
        else:
            print("players initialized")
            for p in players:
                p.seat = self.game.get_next_player_seat()
                p.hand = self.game.get_next_hand()
                print("tiles","".join([Tiles.t136_to_g(x) for x in p.get_hand()]))
                for x in p.hand:
                    if Tiles.t136_to_g(x)=="":
                        print(x)
                print("len:",len(p.get_hand().tiles))

        self.player = players[0]
        self.opponents = players[1:]


    def round_over_message(self) -> Message:
        args = dict()
        for i in range(4):
            args["hai%d" % i] = self.get_player_by_seat(i).hand.stringify()
        return Message.for_type_and_args("RYUUKYOKU", args)

    def send_error(self, connection: socket.socket, message):
        m = Message.for_type_and_args("err", {
            "msg": message
        })
        self.send_messages(connection, m)

    def get_player_by_seat(self, seat_num) -> Player:
        if self.player.seat == seat_num:
            return self.player
        return [x for x in self.opponents if x.seat == seat_num][0]

    def discarded_tile_message(self, seat: int, tile136: int) -> Message|list[Message]:
        seat_str = self.discarded_tile_message_type_by_seat(seat)
        args = dict()

        tiles34 = [Tiles.t136_to_34(x) for x in self.player.get_hand().get_tiles()]
        print("Seat %s discarded: %s" % (seat_str, Tiles.t136_to_g(tile136)))
        if WinCalc.is_fulfilled(tiles34, Tiles.t136_to_34(tile136)):
            print("can call ron for tile: %s"%Tiles.t136_to_g(tile136))
            self.meld_type="ron"
            args['t'] = "12"
            print("activating meld...")
            self.meld_event.set()
        elif self.player.can_call_chii(seat, tile136):
            print("can call chii for tile: %s"%Tiles.t136_to_g(tile136))
            self.meld_type="chii"
            args['t'] = "3"
            print("activating meld...")
            self.meld_event.set()
        elif self.player.can_call_kan(tile136):
            t = "4" if self.player.seat == seat else "2"
            if t == "2":
                print("can call an open kan tile: %s"%Tiles.t136_to_g(tile136))
                self.meld_type = "open kan"
            else:
                print("can call a closed can tile: %s"%Tiles.t136_to_g(tile136))
                self.meld_type = "closed kan"
            args['t'] = t
            print("activating meld...")
            self.meld_event.set()
        elif self.player.can_call_pon(tile136):
            self.meld_type = "pon"
            print("can call pon tile: %s"%Tiles.t136_to_g(tile136))
            args['t'] = "1"
            print("activating meld...")
            self.meld_event.set()

        return Message.for_type_and_args("%s%d" % (seat_str, tile136), args)

    def _wait_for_a_while(self):
        time.sleep(0.5)

    def discarded_tile_message_type_by_seat(self, seat: int):
        lst = ['d', 'e', 'f', 'g']
        return lst[(seat - self.player.seat) % 4]

    def discarded_tile_seat_by_message_type(self, msg_type: str):
        lst = ['d', 'e', 'f', 'g']
        assert msg_type in lst
        return (self.player.seat + lst.index(msg_type)) % 4

    def drawn_tile_message_type_by_seat(self, seat: int):
        lst = ['t', 'u', 'v', 'w']
        return lst[(seat - self.player.seat) % 4]

    def drawn_tile_seat_by_message_type(self, msg_type: str):
        lst = ['t', 'u', 'v', 'w']
        assert msg_type in lst
        return (self.player.seat + lst.index(msg_type)) % 4

    def draw_tile_by_player(self, seat: int, tile136: int) -> Message | list[Message]:
        if self.is_round_over() or self.is_game_over():
            return []
        s = Tiles.t136_to_g(tile136)
        print("player %s draws a tile: %s" % (seat, s))
        t = self.drawn_tile_message_type_by_seat(seat)
        self.get_player_by_seat(seat).draw_tile(tile136)
        if seat==self.player.seat:
            return Message.for_type_and_args("%s%s" % (t, tile136))
        return Message.for_type_and_args(t)

    def discard_tile_by_player(self, seat, tile136: int | None) -> Message | list[Message]:
        if self.is_round_over() or self.is_game_over():
            return []
        player = self.get_player_by_seat(seat)
        if tile136 is None:
            tile136 = player.discard_random()
        else:
            tile136 = player.discard(tile136)
        print("player %s discards a tile: %s" % (seat, Tiles.t136_to_g(tile136)))
        self.last_discarded_tile = tile136
        self.last_discarded_tile_seat = seat
        return self.discarded_tile_message(seat, tile136)

    def seat_to_player_number(self, seat: int):
        return (seat - self.player.seat) % 4

    def call_pon_by_player(self, seat: int, from_seat: int, tile136: int, chankan=False) -> Message:
        print(
            "player %s calls a pon on a tile: %s from player %s" % (seat, Tiles.t136_to_g(tile136), from_seat))

        pon_tiles = self.get_player_by_seat(seat).call_pon(tile136)
        t = 1 if chankan else 0
        called_index = 0
        return Message.for_type_and_args("n", {
            "who": str(self.seat_to_player_number(seat)),
            "from_who": str(self.seat_to_player_number(from_seat)),
            "type": "pon",
            "m": "%d %d %s %s %s" % (t, called_index, pon_tiles[0], pon_tiles[1], pon_tiles[2]),
        })

    def call_chii_by_player(self, seat: int, from_seat: int, tile1: int, tile2: int, tile3: int,
                            tile_called_num=0) -> Message:
        tiles136 = [tile1, tile2, tile3]
        print("player %s calls chii on a tile: %s from player %s" % (
        seat, Tiles.t136_to_g(tiles136[tile_called_num]), from_seat))
        self.get_player_by_seat(seat).call_meld(tiles136[0],tiles136[1:])
        return Message.for_type_and_args("n", {
            "who": str(self.seat_to_player_number(seat)),
            "from_who": str(self.seat_to_player_number(from_seat)),
            "type": "chi",
            "m": "%d %s %s %s" % (tile_called_num, tile1, tile2, tile3),
        })

    def call_kan_by_player(self, seat: int, from_seat: int, tile136: int) -> Message:
        print("player %s calls kan on a tile: %s from player %s" % (seat, Tiles.t136_to_g(tile136), from_seat))
        tiles = self.get_player_by_seat(seat).call_kan(tile136)
        called_index = 0
        return Message.for_type_and_args("n", {
            "who": str(self.seat_to_player_number(seat)),
            "from_who": str(self.seat_to_player_number(from_seat)),
            "type": "kan",
            "m": " %d %s %s %s %s" % (called_index, tiles[0], tiles[1], tiles[2], tiles[3]),
        })

    def initialize_game(self, game_info: GameInfo) -> Message:
        some_nums = [1, 2]
        seed = [game_info.round_number, game_info.honba_sticks, game_info.reach_sticks,
                ] + some_nums + game_info.bonus_tiles
        return Message.for_type_and_args("init", {
            "seed": self.list_stringify(seed),
            "ten": self.list_stringify(game_info.scores),
            "oya": game_info.dealer_seat,
            "hai": self.player.hand.stringify()
        })

    @staticmethod
    def list_stringify(lst: list):
        return ",".join(map(str, lst))

    def join_game(self, game_type) -> list[Message]:
        join_msg = Message.for_type_and_args("GO", {
            "type": game_type[0],
        })
        game_msg = Message.for_type_and_args("TAIKYOKU", {
            'oya': str(self.player.seat),  # 0 - east 4 - north
            'log': "foo"
        })
        op_info = self.opponents_info_message(self.opponents)
        out = [join_msg, game_msg, op_info]
        return out

    def opponents_info_message(self, opponents: list[Player]) -> Message:
        sep = ","
        players = [self.player] + opponents
        return Message.for_type_and_args("UN", {
            "dan": sep.join(map(lambda x: str(x.dan), players)),
            "n0": players[0].name,
            "n1": players[1].name,
            "n2": players[2].name,
            "n3": players[3].name,
        })

    def send_messages(self, conn: socket.socket, messages: Message | list[Message]):
        if isinstance(messages, Message):
            messages = [messages]
        messages=[x for x in messages if
            x.round_number is None or x.round_number==self.game.game_info.round_number]
        conn.sendall(self.message_sep.join(
            map(lambda x: (x.stringify() + self.message_sep), messages)
        ).encode())

    def initialize_player(self, conn: socket.socket,
                          name, tid, sx) -> Message:
        if self.player is not None and self.player.is_initialized():
            self.send_error(conn, "already authenticated")
        elif self.player is not None:
            self.player = None
        message = Message.for_type_and_args("hello", {
            "auth": "123abc",
            "PF4": "1",  # rating
            "nintei": "1"  # new level
        })
        if self.player is None or not self.player.is_initialized():
            print("player init")
            self.player = Player(seat=0, name=name, tid=tid, sx=sx)
        return message

    def create_auth_message(self, token: str):
        message = Message.for_type_and_args("LN", {
        })
        return message


if __name__ == '__main__':
    TenhouServerSocket(server_address).start()
