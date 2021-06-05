from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from ditto.types import User
from ditto.utils.collections import format_list

from ..game import Player, VoteGameState

if TYPE_CHECKING:
    from .game import GameUI

__all__ = ("VoteUI",)


class VoteUI(discord.ui.View):
    def __init__(self, game: GameUI, voters: list[Player[User]]):
        self.game: GameUI = game
        self.voters = voters
        super().__init__(timeout=None)

    @property
    def content(self) -> str:
        return format_list(self.game.game.tooltip + "\nCurrently: {0} {1} voted.", *self.votes)

    @property
    def votes(self) -> dict[Player[User], bool]:
        if isinstance(self.game.game.state, VoteGameState):
            return self.game.game.state.votes
        return {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        player = self.game.game.get_player(interaction.user)
        if player not in self.voters:
            await interaction.response.send_message("You cannot participate in this vote.", ephemeral=True)
            return False
        if player in self.votes:
            await interaction.response.send_message("You have already voted.", ephemeral=True)
            return False
        return True

    async def vote(self, interaction: discord.Interaction, vote: bool) -> None:
        await self.game.store_interaction(interaction)

        player = self.game.game.get_player(interaction.user)
        if player is None:
            raise RuntimeError("How?")
        self.votes[player] = vote

        if self.game.game.state.ready:
            self.game.waiting.set()

        await interaction.message.edit(content=self.content, view=self)

    @discord.ui.button(label="ja!", style=discord.ButtonStyle.danger)
    async def ja(self, item: discord.ui.Button, interation: discord.Interaction) -> None:
        return await self.vote(interation, True)

    @discord.ui.button(label="nein!", style=discord.ButtonStyle.primary)
    async def nein(self, item: discord.ui.Button, interation: discord.Interaction) -> None:
        return await self.vote(interation, False)
