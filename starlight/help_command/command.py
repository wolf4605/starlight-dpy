from __future__ import annotations

from functools import cached_property
from typing import Optional, List, Any, Union, Dict, TypeVar, Mapping, Type

import discord
from discord.ext import commands

from .view import HelpMenuCommand, HelpMenuProvider, HelpMenuGroup, HelpMenuError, HelpMenuCog, MenuHomeButton
from ..views.pagination import ViewEnhanced

__all__ = (
    "MenuHelpCommand",
)

T = TypeVar('T')
_Command = commands.Command[Any, ..., Any]
_MappingBotCommands = Dict[Optional[commands.Cog], List[_Command]]
_OptionalFormatReturns = Union[discord.Embed, Dict[str, Any], str]


class MenuHelpCommand(commands.HelpCommand):
    def __init__(self, *,
                 per_page: int = 6,
                 sort_commands: bool = True,
                 no_documentation: str = "No Documentation",
                 no_category: str = "No Category",
                 accent_color: Union[discord.Color, int] = discord.Color.blurple(),
                 error_color: Union[discord.Color, int] = discord.Color.red(),
                 pagination_buttons: Optional[Mapping[str, discord.ui.Button]] = None,
                 cls_home_button: Type[MenuHomeButton] = MenuHomeButton,
                 **options):
        super().__init__(**options)
        self.no_category: str = no_category
        self.per_page: int = per_page
        self.accent_color: Union[discord.Color, int] = accent_color
        self.error_color: Union[discord.Color, int] = error_color
        self.no_documentation: str = no_documentation
        self.__sort_commands: bool = sort_commands
        self.view_provider: HelpMenuProvider = HelpMenuProvider(self)
        self.original_message: Optional[discord.Message] = None
        self._pagination_buttons = pagination_buttons
        self._cls_home_button = cls_home_button

    @cached_property
    def pagination_buttons(self) -> Mapping[str, discord.ui.Button]:
        return self._pagination_buttons or {
            "start_button": discord.ui.Button(emoji="⏪"),
            "previous_button": discord.ui.Button(emoji="◀️"),
            "stop_button": discord.ui.Button(emoji="⏹️"),
            "next_button": discord.ui.Button(emoji="▶️"),
            "end_button": discord.ui.Button(emoji="⏩")
        }

    def get_command_signature(self, command: _Command, /) -> str:
        return f'{self.context.clean_prefix}{command.qualified_name} {command.signature}'

    def format_command_brief(self, cmd: _Command) -> str:
        return f"{self.get_command_signature(cmd)}\n{cmd.short_doc or self.no_documentation}"

    async def format_group_detail(self, view: HelpMenuGroup) -> _OptionalFormatReturns:
        group = view.group
        subcommands = "\n".join([self.format_command_brief(cmd) for cmd in group.commands])
        description = group.help or self.no_documentation
        return discord.Embed(
            title=self.get_command_signature(group),
            description=f"{description}\n\n**Subcommands**\n{subcommands}",
            color=self.accent_color
        )

    async def format_command_detail(self, view: HelpMenuCommand) -> _OptionalFormatReturns:
        cmd = view.command
        return discord.Embed(
            title=self.get_command_signature(cmd),
            description=cmd.help,
            color=self.accent_color
        )

    async def format_error_detail(self, view: HelpMenuError) -> _OptionalFormatReturns:
        return discord.Embed(
            title="Something went wrong!",
            description=str(view.error),
            color=self.error_color
        )

    def resolve_cog_name(self, cog: Optional[commands.Cog]):
        return getattr(cog, "qualified_name", None) or self.no_category

    async def __normalized_kwargs(self, callback, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        formed_interface = await discord.utils.maybe_coroutine(callback, *args, **kwargs)
        if isinstance(formed_interface, dict):
            return formed_interface
        elif isinstance(formed_interface, discord.Embed):
            return {"embed": formed_interface}
        return {"content": formed_interface}

    async def _form_front_bot_menu(self, cogs: List[commands.Cog]) -> Dict[str, Any]:
        return await self.__normalized_kwargs(self.format_front_bot_menu, cogs)

    async def _form_command_detail(self, view: HelpMenuCommand) -> Dict[str, Any]:
        return await self.__normalized_kwargs(self.format_command_detail, view)

    async def _form_group_detail(self, view: HelpMenuGroup) -> Dict[str, Any]:
        return await self.__normalized_kwargs(self.format_group_detail, view)

    async def _form_error_detail(self, view: HelpMenuError) -> Dict[str, Any]:
        return await self.__normalized_kwargs(self.format_error_detail, view)

    async def _filter_commands(self,
                               mapping: Mapping[Optional[commands.Cog], List[_Command]]
                               ) -> Mapping[Optional[commands.Cog], List[_Command]]:
        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=self.__sort_commands)
            if filtered:
                yield cog, filtered

    async def send_bot_help(self, mapping: Mapping[Optional[commands.Cog], List[_Command]], /) -> None:
        filtered_commands = {cog: cmds async for cog, cmds in self._filter_commands(mapping)}
        view = await self.view_provider.provide_bot_view(filtered_commands)
        menu_kwargs = await self._form_front_bot_menu(mapping)
        menu_kwargs.setdefault("view", view)
        message = await self.get_destination().send(**menu_kwargs)
        await self.initiate_view(view=view, message=message, context=self.context)

    async def initiate_view(self, view: Optional[ViewEnhanced], **kwargs) -> None:
        if isinstance(view, ViewEnhanced):
            await view.start(**kwargs)
            self.original_message = view.message
            return

        self.original_message = await self.get_destination().send(view=view, **kwargs)

    async def send_cog_help(self, cog: commands.Cog, /) -> None:
        cmds = await self.filter_commands(cog.walk_commands(), sort=self.__sort_commands)
        view = await self.view_provider.provide_cog_view(cog, cmds)
        await self.initiate_view(view)

    async def send_command_help(self, command: _Command, /) -> None:
        view = await self.view_provider.provide_command_view(command)
        await self.initiate_view(view)

    async def send_group_help(self, group: _Command, /) -> None:
        view = await self.view_provider.provide_group_view(group)
        await self.initiate_view(view)

    async def send_error_message(self, error: str, /) -> None:
        view = await self.view_provider.provide_error_view(error)
        await self.initiate_view(view)

    async def format_front_bot_menu(self, mapping: _MappingBotCommands) -> _OptionalFormatReturns:
        embed = discord.Embed(
            title="Help Command",
            description=self.context.bot.description or None,
            color=self.accent_color
        )
        data = [(cog, cmds) for cog, cmds in mapping.items()]
        data.sort(key=lambda d: self.resolve_cog_name(d[0]))
        for cog, cmds in data:
            name_resolved = self.resolve_cog_name(cog)
            value = getattr(cog, "description", None) or self.no_documentation
            name = f"{name_resolved} ({len(cmds)})"
            embed.add_field(name=name, value=value)

        return embed

    async def format_cog_page(self, view: HelpMenuCog, data: List[_Command]) -> _OptionalFormatReturns:
        return discord.Embed(
            title=self.resolve_cog_name(view.cog),
            description="\n".join([self.format_command_brief(cmd) for cmd in data]),
            color=self.accent_color
        )