"""根据当前对局提供打法建议。"""

from .agent import stream_game_answer
from .state import GameState

__all__ = ["GameState", "stream_game_answer"]
