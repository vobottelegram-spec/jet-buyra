import os
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()
@dataclass
class Config:
    bot_token:str
    tnumber_key:str
    db_path:str='jetnumber.db'
    owner_ids:tuple[int,...]=(7048466991,858897695)
    tnumber_base:str='https://b.tnumber.site'
    okaypay_id:str=''
    okaypay_token:str=''
    okaypay_callback_url:str=''
    okaypay_return_url:str=''
    biyora_url:str=''
    biyora_key_id:str='jetnumber'
    biyora_secret:str=''
    biyora_cafile:str=''
def load_config():
    owners=tuple(int(x.strip()) for x in os.getenv('OWNER_IDS','7048466991,858897695').split(',') if x.strip())
    return Config(os.getenv('BOT_TOKEN',''),os.getenv('TNUMBER_API_KEY',''),os.getenv('DATABASE_PATH','jetnumber.db'),owners or (7048466991,858897695),os.getenv('TNUMBER_BASE','https://b.tnumber.site'),os.getenv('OKAYPAY_APP_ID',''),os.getenv('OKAYPAY_TOKEN',''),os.getenv('OKAYPAY_CALLBACK_URL',''),os.getenv('OKAYPAY_RETURN_URL',''),biyora_url=os.getenv('BIYORA_URL',''),biyora_key_id=os.getenv('BIYORA_KEY_ID','jetnumber'),biyora_secret=os.getenv('BIYORA_SECRET',''),biyora_cafile=os.getenv('BIYORA_CAFILE',''))
