import requests
import config, json
from iex import IEXStock
from helpers import format_number
from datetime import datetime, timedelta
import pandas as pd

print(config.IEX_TOKEN)
stock = IEXStock(config.IEX_TOKEN, 'MSFT', environment='sandbox')
print(stock)

logo = stock.get_logo()
print(logo)

stats = stock.get_stats()
print(stats)


