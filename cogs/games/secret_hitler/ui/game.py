from __future__ import annotations

import asyncio
from collections.abc import Collection
from typing import TYPE_CHECKING, Union

import discord
from ditto.types import User

from ..game import *
from .discard import DiscardUI
from .peek import PeekUI
from .player import PlayerUI
from .select import SelectUI
from .vote import VoteUI

if TYPE_CHECKING:
    from .select import *

__all__ = ("GameUI",)

SLEEP_FOR = 5


class ResendMessageButton(discord.ui.Button["GameUI"]):
    def __init__(self) -> None:
        super().__init__(style=discord.ButtonStyle.secondary, label="Re-send Game")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view.host:
            await interaction.response.send_message("Only the host can re-send the game message.", ephemeral=True)
            return

        await self.view.resend()
        await interaction.response.defer()


class ResendViewButton(discord.ui.Button["GameUI"]):
    def __init__(self) -> None:
        super().__init__(style=discord.ButtonStyle.secondary, label="Re-send Menu")

    async def callback(self, interaction: discord.Interaction):
        if not isinstance(self.view.view, PeekUI):
            await interaction.response.send_message("There is currently not a hidden menu.", ephemeral=True)
            return

        player = self.view.game.get_player(interaction.user)
        if player is not self.view.view.target:
            await interaction.response.send_message(
                "Only the hidden menu target can refresh the menu.", ephemeral=True
            )
            return

        await interaction.response.send_message(self.view.game.tooltip, view=self.view.view, ephemeral=True)


class StopGameButton(discord.ui.Button["GameUI"]):
    def __init__(self) -> None:
        super().__init__(style=discord.ButtonStyle.danger, label="Stop Game")

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.view.host:
            await interaction.response.send_message("Only the host can stop the game.", ephemeral=True)
            return

        self.view.cancel()
        await interaction.response.defer()


class BlankButton(discord.ui.Button["GameUI"]):
    def __init__(self) -> None:
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", disabled=True)


class GameUI(discord.ui.View):
    children: list[discord.ui.Button]

    def __init__(
        self, message: discord.Message, host: User, users: Collection[User], games: dict[int, discord.ui.View]
    ):
        self.host: User = host
        self.game: Game[User] = Game[User](users)
        self.interactions: dict[User, discord.Interaction] = {}
        self.message = message
        self.games = games
        self.waiting = asyncio.Event()
        self.view: Optional[Union[SelectUI, VoteUI]] = None

        super().__init__(timeout=None)

        self.add_item(ResendMessageButton())
        self.add_item(ResendViewButton())
        self.add_item(BlankButton())
        self.add_item(BlankButton())
        self.add_item(StopGameButton())

    async def store_interaction(self, interaction: discord.Interaction) -> None:
        player = self.game.get_player(interaction.user)
        if player is not None:
            self.interactions[player.identifier] = interaction
        await interaction.response.defer(ephemeral=True)

    async def resend(self):
        old_message = self.message
        self.message = await self.channel.send(self.game.message, view=self)
        await old_message.delete()

    def stop(self) -> None:
        del self.games[self.message.channel.id]
        super().stop()

    def cancel(self) -> None:
        self.game.state = GameCancelled(self.game)
        if not self.waiting.is_set():
            self.waiting.set()
        self.stop()

    async def send_view(self) -> None:
        if isinstance(self.view, SelectUI):
            if isinstance(self.view, PeekUI):
                interaction = self.interactions.pop(self.view.target.identifier)
                await interaction.followup.send(self.game.tooltip, view=self.view, ephemeral=True)
            else:
                await self.channel.send(self.game.tooltip, reference=self.message, view=self.view)

        elif isinstance(self.view, VoteUI):
            await self.channel.send(self.game.tooltip, reference=self.message, view=self.view)

    async def update(self) -> None:
        state = self.game.state

        # determine view type.
        if isinstance(state, (SelectGameState, PolicyListPeek, PlayerWasInvestigated)):
            # Determine target
            if isinstance(self.game.state, ChancellorDiscardsPolicy):
                target = self.game.chancellor
            elif isinstance(self.game.state, PlayerToBeChancellor):
                target = self.game.state.president
            else:
                target = self.game.president

            # Determine view type.
            if isinstance(state, PolicyListPeek):
                self.view = PeekUI(self, target, state.policies)
            elif isinstance(state, PlayerWasInvestigated):
                self.view = PeekUI(self, target, [state.player.party])
            else:
                if isinstance(state.selectable[0], Player):
                    self.view = PlayerUI(self, target, state.selectable)
                else:
                    self.view = DiscardUI(self, target, state.selectable)

        elif isinstance(state, VoteGameState):
            self.view = VoteUI(self, state.voters)

        await self.message.edit(content=self.game.message, view=self)
        if self.view is not None:
            await self.send_view()

    async def play(self) -> None:
        while not self.game.game_over:
            await self.update()
            ready = self.game.state.ready
            if ready is Skip:
                await asyncio.sleep(SLEEP_FOR)
            elif not ready:
                self.waiting.clear()
                await self.waiting.wait()
            self.game.next_state()
        await self.update()
        self.stop()

    @property
    def channel(self) -> discord.TextChannel:
        return self.message.channel  # type: ignore

    @classmethod
    async def start(
        cls,
        message: discord.Message,
        host: User,
        users: dict[User, discord.Interaction],
        games: dict[int, discord.ui.View],
    ) -> None:
        games[message.channel.id] = self = cls(message, host, users.keys(), games)

        for player in self.game.players:
            content = SECRET_MESSAGES[self.game.player_count][player.role]
            if player.role is Role.Fascist:
                content = content.format(
                    self.game.hitler, *[user for user in self.game.fascists if user != player.identifier]
                )
            await users[player.identifier].followup.send(content, ephemeral=True)

        await self.play()
