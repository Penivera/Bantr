from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from app.core.constants import POLL_TIMEOUT_SECONDS
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class PlayerPoll:
    poll_id: str
    bet_id: str
    chat_id: int
    player: str
    event_type: str  # "goal", "card"
    event_description: str
    participants: list[str]
    votes_yes: list[str] = field(default_factory=list)
    votes_no: list[str] = field(default_factory=list)
    message_id: int = 0
    resolved: bool = False
    result: bool | None = None

    def has_voted(self, username: str) -> bool:
        return username in self.votes_yes or username in self.votes_no

    def vote(self, username: str, vote_yes: bool) -> bool:
        if self.has_voted(username):
            return False
        if vote_yes:
            self.votes_yes.append(username)
        else:
            self.votes_no.append(username)
        return True

    def is_consensus(self) -> bool:
        needed = max(1, len(self.participants))
        return len(self.votes_yes) >= needed or len(self.votes_no) >= needed


class PollManager:
    def __init__(self):
        self._polls: dict[str, PlayerPoll] = {}
        self._timers: dict[str, asyncio.Task] = {}

    def create(self, bet_id: str, chat_id: int, player: str,
               event_type: str, event_description: str,
               participants: list[str]) -> PlayerPoll:
        poll_id = f"poll_{bet_id}_{event_type}_{len(self._polls)}"
        poll = PlayerPoll(
            poll_id=poll_id, bet_id=bet_id, chat_id=chat_id,
            player=player, event_type=event_type,
            event_description=event_description,
            participants=participants,
        )
        self._polls[poll_id] = poll
        self._start_timer(poll_id)
        return poll

    def get(self, poll_id: str) -> PlayerPoll | None:
        return self._polls.get(poll_id)

    def resolve(self, poll_id: str) -> PlayerPoll | None:
        poll = self._polls.pop(poll_id, None)
        if poll:
            poll.resolved = True
            poll.result = len(poll.votes_yes) > len(poll.votes_no)
            t = self._timers.pop(poll_id, None)
            if t:
                t.cancel()
        return poll

    def active_for_bet(self, bet_id: str) -> list[PlayerPoll]:
        return [p for p in self._polls.values() if p.bet_id == bet_id and not p.resolved]

    def _start_timer(self, poll_id: str) -> None:
        async def _timeout():
            await asyncio.sleep(POLL_TIMEOUT_SECONDS)
            poll = self._polls.pop(poll_id, None)
            if poll:
                poll.resolved = True
                poll.result = len(poll.votes_yes) > len(poll.votes_no)
                logger.info("poll_timeout_resolved", poll_id=poll_id, yes=len(poll.votes_yes), no=len(poll.votes_no))

        self._timers[poll_id] = asyncio.ensure_future(_timeout())


poll_manager = PollManager()
