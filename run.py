from discord.ext.alternatives import converter_dict

from bot import BotBase, Config

Config._bot = bot = BotBase()
bot.run()
