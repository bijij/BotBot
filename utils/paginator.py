"""
MIT License

Copyright (c) 2021 Joshua Butt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from typing import Any, Dict, NamedTuple, List

import discord
from discord.ext import commands, menus


class EmbedPage(NamedTuple):
    description: List[str]
    fields: List[Dict[str, Any]]


class PaginatorSource(commands.Paginator, menus.PageSource):

    def is_paginating(self):
        return self.get_max_pages() > 1

    def get_max_pages(self):
        return len(self._pages) + (self._count != 0)

    async def get_page(self, page_number: int):
        return self.pages[page_number]


class EmbedPaginator(discord.Embed, PaginatorSource):
    def __init__(self, max_size=5000, max_description=2048, max_fields=25, **kwargs):

        description = kwargs.pop('description', '')
        discord.Embed.__init__(self, **kwargs)

        self.prefix = None
        self.suffix = None

        self.max_size = max_size
        self.max_description = max_description
        self.max_fields = max_fields

        self.clear()

        for line in description.split('\n'):
            self.add_line(line)

    def clear(self):
        self._current_page = EmbedPage([], [])
        self._description_count = 0
        self._count = 0
        self._pages = []

    def add_line(self, line='', *, empty=False):
        if len(line) > self.max_description:
            raise RuntimeError(f'Line exceeds maximum description size {self.max_description}')

        if self._count + len(line) + 1 > self.max_size:
            self.close_page()

        if self._description_count + len(line) + 1 > self.max_description:
            self.close_page()

        self._count += len(line) + 1
        self._description_count += len(line) + 1
        self._current_page.description.append(line)

        if empty:
            self._current_page.description.append('')
            self._count += 1

    @property
    def fields(self):
        fields = []
        for page in self._pages:
            for field in page.fields:
                fields.append(discord.embeds.EmbedProxy(field))
        return fields

    def add_field(self, *, name, value, inline=False):
        if len(name) + len(value) > self.max_size:
            raise RuntimeError(f'Field exceeds maximum page size {self.max_size}')

        if len(self._current_page.fields) >= self.max_fields:
            self.close_page()

        if self._count + len(name) + len(value) > self.max_size:
            self.close_page()

        self._count += len(name) + len(value)
        self._current_page.fields.append(dict(name=name, value=value, inline=inline))

    def close_page(self):
        self._pages.append(self._current_page)
        self._current_page = EmbedPage([], [])
        self._description_count = 0
        self._count = 0

    def _format_page(self, page):
        embed = discord.Embed.from_dict(self.to_dict())
        embed.description = '\n'.join(page.description)

        if self._pages.index(page) >= 1 and embed.author.name:
            embed.set_author(
                name=embed.author.name + ' cont.',
                url=embed.author.url,
                icon_url=embed.author.icon.url
            )

        for field in page.fields:
            embed.add_field(**field)

        return embed

    async def format_page(self, menu, page):
        return page

    @property
    def pages(self):
        if len(self._current_page.description) > 0 or len(self._current_page.fields) > 0:
            self.close_page()

        return [self._format_page(page) for page in self._pages]

    def __repr__(self):
        fmt = '<EmbedPaginator max_size: {0.max_size}>'
        return fmt.format(self)
