import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
from datetime import datetime
import json

base_url = "http://ergast.com/api/f1"
endpoint = "2023/results"
limit = 100 
offset = 0
url = f"{base_url}/{endpoint}.json?limit={limit}&offset={offset}"

response = requests.get(url)
data = response.json()
with open("data.json", "w") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)
