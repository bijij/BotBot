from discord.ext.alternatives import converter_dict, menus_remove_reaction, silent_delete

from bot import BotBase, Config

Config._bot = bot = BotBase()
bot.run()
