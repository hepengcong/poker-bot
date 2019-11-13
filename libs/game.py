from enum import IntEnum
from functools import wraps
from .card import Card
from .pokerCmp import poker7
import random

status_names = ["PREFLOP", "FLOP", "TURN", "RIVER", "END"]


class GameStatus(IntEnum):
    WAITFORPLAYERREADY = 1
    RUNNING = 2
    CONTINUING = 3


class RoundStatus(IntEnum):
    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3
    END = 4


def status(ss):
    def dec(func):
        def wrapper(self, *args, **kwargs):
            for s in ss:
                if self.gameStatus == s:
                    return func(self, *args, **kwargs)
            return -1
        return wrapper
    return dec


class Game(object):
    def __init__(self, maxPlayer):
        assert maxPlayer > 1
        self.maxPlayer = maxPlayer
        self.players = [Player(i) for i in range(maxPlayer)]
        self.gameStatus = GameStatus.WAITFORPLAYERREADY
        self.numOfPlayer = 0
        self.deck = Deck()
        self.btn = -1
        self.ante = 20
        self.exePos = -1
        self.pubCards = []

    @staticmethod
    def build(maxplayer):
        pass

    def getCardsByPos(self, pos):
        player = self.players[pos]
        return player.cards

    def get_round_status_name(self):
        return status_names[int(self.roundStatus)]

    def get_exe_pos(self):
        return self.exePos

    @status([GameStatus.WAITFORPLAYERREADY])
    def setPlayer(self, pos, chip):
        player = self.players[pos]
        # is occupied ?
        if player.active:
            return -1

        player.active = True
        player.chip = chip
        self.numOfPlayer = self.numOfPlayer + 1
        return 0

    @status([GameStatus.WAITFORPLAYERREADY])
    def setReady(self, pos):
        player = self.players[pos]

        if player.active:
            player.ready = True
            return 0
        return -1

    @status([GameStatus.WAITFORPLAYERREADY, GameStatus.CONTINUING])
    def start(self):
        for i in range(0, self.maxPlayer):
            if (self.players[i].active != self.players[i].ready):
                return -1
        # all the players are ready
        self.gameStatus = GameStatus.RUNNING
        self.roundStatus = RoundStatus.PREFLOP

        # deal all players
        for player in self.players:
            player.cards[0] = self.deck.getCard()
            player.cards[1] = self.deck.getCard()

        # blind
        self.btn = self.findNextActivePlayer(self.btn)
        self.sb = self.findNextActivePlayer(self.btn)
        self.bb = self.findNextActivePlayer(self.sb)
        self.utg = self.findNextActivePlayer(self.bb)

        # a flag for end of one round
        self.exePos = self.utg
        self.nextRound = self.bb

        self.putChip(self.sb, self.ante / 2, 'SB')
        self.putChip(self.bb, self.ante, 'BB')
        self.lastBet = self.ante
        self.permitCheck = False

        return 0

    def findNextActivePlayer(self, pos):
        pos += 1
        count = 0
        while(self.players[pos].active == False or self.players[pos].fold or self.players[pos].allin):
            pos = (pos + 1) % self.maxPlayer
            count += 1

            # nobody can do action
            if (count > self.maxPlayer):
                return -1
        return pos

    def invokeNextPlayer(self):
        r = self.findNextActivePlayer(self.exePos)
        if r == -1:
            self.gend()
        else:
            self.exePos = r

        # touch the bound
        if self.roundStatus != RoundStatus.END and self.exePos == self.nextRound:
            if self.roundStatus == RoundStatus.PREFLOP:
                self.flop()
            elif self.roundStatus == RoundStatus.FLOP:
                self.turn()
            elif self.roundStatus == RoundStatus.TURN:
                self.river()
            elif self.roundStatus == RoundStatus.RIVER:
                self.end()
            self.roundStatus = RoundStatus(self.roundStatus.value + 1)
            self.lastBet = 0
            # sb first
            self.exePos = self.sb

    def gend(self):
        # continue round until end
        self.roundStatus
        if self.roundStatus.value < RoundStatus.FLOP.value:
            self.flop()
        if self.roundStatus.value < RoundStatus.TURN.value:
            self.turn()
        if self.roundStatus.value < RoundStatus.RIVER.value:
            self.river()
        if self.roundStatus.value < RoundStatus.END.value:
            self.end()

    def flop(self):
        self.pubCards = [self.deck.getCard() for i in range(3)]

    def turn(self):
        self.pubCards.append(self.deck.getCard())

    def river(self):
        self.pubCards.append(self.deck.getCard())

    def end(self):
        players = []
        for p in self.players:
            if p.active:
                p.chip = p.chip - p.chipBet
                if p.fold == False:
                    p.setRank(self.pubCards)
                    players.append(p)

        def take_rank(p):
            return p.rank
        players.sort(key=take_rank, reverse=True)
        self.roundStatus = RoundStatus.END
        self.gameStatus = GameStatus.CONTINUING

    def get_active_player_num(self):
        count = 0
        for player in self.players:
            if player.active and player.fold == False:
                count += 1
        return count

    def putChip(self, pos, num, action):
        player = self.players[pos]
        if player.chip < num:
            return -1
        # allin
        elif player.chip == num:
            player.allin = True
            action = 'ALLIN'
        player.chipBet = num
        return 0

    @status([GameStatus.RUNNING])
    def pbet(self, pos, num):
        if (pos != self.exePos or num < self.ante or self.lastBet != 0):
            return -1

        self.putChip(pos, num, 'BET')
        self.lastBet = num
        self.permitCheck = True
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pcall(self, pos):
        if pos != self.exePos or self.putChip(pos, self.lastBet, 'CALL') < 0:
            return -1
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pfold(self, pos):
        if (pos != self.exePos):
            return -1
        self.players[pos].fold = True

        # end of a game
        if self.get_active_player_num() == 1:
            self.end()
        else:
            self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pcheck(self, pos):
        if (pos != self.exePos or self.permitCheck == False):
            return -1
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def praise(self, pos, num):
        if (pos != self.exePos or num < self.lastBet * 2):
            return -1

        self.nextRound = self.exePos
        self.lastBet = num
        self.permitCheck = False
        self.putChip(pos, num, 'RAISE')
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pallin(self, pos):
        if (pos != self.exePos):
            return -1

        # does allin raise the chip?
        if self.lastBet < self.players[pos].chip:
            self.nextRound = self.exePos
            self.lastBet = self.players[pos].chip
        self.permitCheck = False
        self.putChip(pos, self.players[pos].chip, 'ALLIN')
        self.invokeNextPlayer()
        return 0

    def getJSON(self):
        return 'temp'


class Player(object):
    def __init__(self, pos):
        self.chip = 0
        self.chipBet = 0
        self.cards = [0] * 2
        self.active = False  # join a game
        self.ready = False
        self.fold = False
        self.allin = False
        self.pos = pos

    def setRank(self, pubCards):
        def cardToStr(card):
            return str(card)
        maxRank = poker7(map(cardToStr, self.cards + pubCards))
        self.rank = maxRank['rank']
        self.hand = maxRank['hand']


class Deck(object):
    def __init__(self):
        self.deckCards = list(range(0, 52))
        self.shuffle()

    def getCard(self):
        num = self.deckCards[self.i]
        card = Card(int(num / 13), num % 13 + 1)
        self.i = self.i + 1
        return card

    def shuffle(self):
        random.shuffle(self.deckCards)
        self.i = 0
