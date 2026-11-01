import os 
from urllib.parse import quote_plus 
from dotenv import load_dotenv 
from platformdirs import user_data_dir 

load_dotenv(override=True)

CURRENT_FILE = os.path.abspath(__file__)
BACKEND_DIR = os.path.dirname(os.path.dirname(CURRENT_FILE))

APP_NAME = "FEACopilot"
APP_AUTHOR = "PhoenixAI"
APP_DATA_DIR = user_data_dir(appname=APP_NAME, appauthor=APP_AUTHOR)
ASSETS_DIR = os.path.join(APP_DATA_DIR, "assets")
SIMULATION_ARTIFACTS_DIR = os.path.join(APP_DATA_DIR, "simulation_artifacts")

SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{os.getenv('DB_USER')}:{quote_plus(os.getenv('DB_PASSWORD', ''))}"
    f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
) 



