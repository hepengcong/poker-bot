from enum import IntEnum
from functools import wraps
from .card import Card
from .pokerCmp import poker7
import random
from typing import List, Dict
from .player import Player, PlayerStatus


class GameStatus(IntEnum):
    WAITING = 1
    RUNNING = 2


class RoundStatus(IntEnum):
    PREFLOP = 0
    FLOP = 1
    TURN = 2
    RIVER = 3
    END = 4


def status(ss):
    def dec(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.game_status in ss:
                return func(self, *args, **kwargs)
            # TODO: using exception or error to handle this
            return -1
        return wrapper
    return dec


class Result:
    def __init__(self):
        self.chip_changes: Dict[Player, int] = dict()

    def add_result(self, player: Player, chip: int):
        self.chip_changes[player] = chip

    def win_bet(self, player: Player, chip: int):
        self.chip_changes[player] += chip

    def lose_bet(self, player: Player, chip: int):
        self.chip_changes[player] -= chip
    
    def execute(self):
        for player, chip in self.chip_changes.items():
            player.chip += chip


class Game(object):
    def __init__(self):
        self.players: List[Player] = []
        self.game_status: GameStatus = GameStatus.WAITING
        self.roundStatus: RoundStatus = None
        self.nplayers = 0
        self.deck: Deck = None
        self.btn = 0
        self.sb = 0
        self.bb = 0
        self.utg = 0
        self.ante = 0
        self.exe_pos = 0
        self.total_pot = 0
        self.pub_cards = []
        self.highest_bet = 0
        self.result = Result()

    def init_game(self, players: List[Player], ante: int, btn: int):
        self.players = players
        for player in self.players:
            player.init()
        self.roundStatus = RoundStatus.PREFLOP
        self.nplayers = len(self.players)
        self.deck = Deck()
        self.btn = btn
        self.ante = ante
        self.exe_pos = -1
        self.pub_cards = []
        self.highest_bet = 0
        self.result = Result()
        self.total_pot = 0

    def getCardsByPos(self, pos):
        player = self.players[pos]
        return player.cards

    def get_round_status_name(self):
        return self.roundStatus.name

    def get_exe_pos(self):
        return self.exe_pos

    @status([GameStatus.WAITING])
    def start(self, players: List[Player], ante: int, btn: int):
        self.init_game(players, ante, btn)

        self.game_status = GameStatus.RUNNING

        # deal all players
        for player in self.players:
            player.cards[0] = self.deck.getCard()
            player.cards[1] = self.deck.getCard()

        # blind
        self.sb = self.findNextActivePlayer(self.btn)
        self.bb = self.findNextActivePlayer(self.sb)
        self.utg = self.findNextActivePlayer(self.bb)

        # a flag for end of one round
        self.exe_pos = self.utg
        self.nextRound = self.utg

        self.putChip(self.sb, self.ante // 2, 'SB')
        self.putChip(self.bb, self.ante, 'BB')
        self.highest_bet = self.ante

        return 0

    def findNextActivePlayer(self, pos):
        new_pos = (pos + 1) % self.nplayers
        while not(self.players[pos].active and self.players[pos].is_playing()):
            if new_pos == pos:
                return -1
            new_pos = (new_pos + 1) % self.nplayers

        return new_pos if new_pos != pos else -1

    def invokeNextPlayer(self):
        r = self.findNextActivePlayer(self.exe_pos)
        if r == -1:
            self.gend()
        else:
            self.exe_pos = r

        # touch the bound
        if self.roundStatus != RoundStatus.END and self.exe_pos == self.nextRound:
            if self.roundStatus == RoundStatus.PREFLOP:
                self.flop()
            elif self.roundStatus == RoundStatus.FLOP:
                self.turn()
            elif self.roundStatus == RoundStatus.TURN:
                self.river()
            elif self.roundStatus == RoundStatus.RIVER:
                self.end()
                return
            self.roundStatus = RoundStatus(self.roundStatus.value + 1)
            # sb first
            self.exe_pos = self.sb
            self.nextRound = self.sb

    def gend(self):
        # continue round until end
        if self.roundStatus.value < RoundStatus.FLOP.value:
            self.flop()
        if self.roundStatus.value < RoundStatus.TURN.value:
            self.turn()
        if self.roundStatus.value < RoundStatus.RIVER.value:
            self.river()
        if self.roundStatus.value < RoundStatus.END.value:
            self.end()

    def flop(self):
        self.pub_cards = [self.deck.getCard() for i in range(3)]

    def turn(self):
        self.pub_cards.append(self.deck.getCard())

    def river(self):
        self.pub_cards.append(self.deck.getCard())

    def win_pot(self, winners: List[Player], exclude_players: List[Player]):
        """Calculate how many chips the `winner` wins and set result for all players

        Args:
            winners (List[Player]): the winners, if more than one player, they split the pot.
                Note that the winners are sorted in **descending** order of their bet, which
                is crucial beacause we always want to deal with the main pot first
            exclude_players (List[Player]): players in this list will not lose chips
                to `winner`, because they have a bigger hand
        """
        n_winners = len(winners)
        for player in self.players:
            if player in winners or player in exclude_players:
                continue
            for winner in winners:
                could_win = min(player.chipBet, winner.chipBet)
                self.result.win_bet(winner, could_win // n_winners)
                self.result.lose_bet(player, could_win // n_winners)
                player.chipBet -= could_win

    def end(self):
        # Initialize self.result
        for player in self.players:
            self.result.add_result(player, 0)
        
        active_players: List[Player] = list(filter(lambda p: p.active and not p.is_fold(), self.players))
        if len(active_players) == 0:
            raise RuntimeError("No active player?")

        # Only when there are more than two active players, comparision is needed
        if len(active_players) >= 2:
            for p in active_players:
                hand, rank = poker7(list(map(lambda card: str(card), p.cards + self.pub_cards)))
                p.set_rank_and_hand(rank, hand)
            active_players.sort(key=lambda p: p.chipBet, reverse=False)
            active_players.sort(key=lambda p: p.rank, reverse=True)

        winner_players = []
        exclude_players = []
        last_rank = active_players[0].rank
        for p in active_players:
            if p.rank == last_rank:
                winner_players.append(p)
            else:
                self.win_pot(winner_players, exclude_players)
                exclude_players += winner_players.copy()
                winner_players = [p]
                last_rank = p.rank
        self.win_pot(winner_players, exclude_players)

        self.roundStatus = RoundStatus.END
        self.game_status = GameStatus.WAITING

    def get_active_player_num(self):
        count = 0
        for player in self.players:
            if player.active and not player.is_fold():
                count += 1
        return count

    def putChip(self, pos, num, action):
        player = self.players[pos]
        remaining_chip = player.get_remaining_chip()
        if remaining_chip < num:
            return -1
        if remaining_chip == num:
            player.set_allin()
        player.chipBet += num
        self.total_pot += num
        return 0

    def is_check_permitted(self, pos):
        return self.players[pos].chipBet >= self.highest_bet

    @status([GameStatus.RUNNING])
    def pcall(self, pos):
        if pos != self.exe_pos or self.putChip(pos, self.highest_bet - self.players[pos].chipBet, 'CALL') < 0:
            return -1
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pfold(self, pos):
        if pos != self.exe_pos:
            return -1
        self.players[pos].set_fold()

        # end of a game
        if self.get_active_player_num() == 1:
            self.end()
        else:
            self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pcheck(self, pos):
        if pos != self.exe_pos or not self.is_check_permitted(pos):
            return -1
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def praise(self, pos, num):
        # TODO: check valid raise: the diff is bigger than the last diff
        if pos != self.exe_pos:
            return -1

        self.nextRound = self.exe_pos
        self.putChip(pos, num, 'RAISE')
        self.highest_bet = self.players[pos].chipBet
        self.invokeNextPlayer()
        return 0

    @status([GameStatus.RUNNING])
    def pallin(self, pos):
        if pos != self.exe_pos:
            return -1

        # does allin raise the chip?
        if self.players[pos].chip > self.highest_bet:
            self.highest_bet = self.players[pos].chip
            self.nextRound = self.exe_pos
        self.putChip(pos, self.players[pos].get_remaining_chip(), 'ALLIN')
        self.invokeNextPlayer()
        return 0

    def getJSON(self):
        return 'temp'


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
