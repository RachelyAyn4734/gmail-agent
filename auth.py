import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from cryptography.fernet import Fernet

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']
TOKEN_PATH = 'token.enc'
KEY_PATH = 'token.key'
CREDENTIALS_PATH = 'credentials.json'

def generate_key():
    if not os.path.exists(KEY_PATH):
        key = Fernet.generate_key()
        with open(KEY_PATH, 'wb') as f:
            f.write(key)

def encrypt_token(token):
    key = open(KEY_PATH, 'rb').read()
    f = Fernet(key)
    with open(TOKEN_PATH, 'wb') as f_enc:
        f_enc.write(f.encrypt(pickle.dumps(token)))

def decrypt_token():
    if not os.path.exists(TOKEN_PATH) or not os.path.exists(KEY_PATH):
        return None
    key = open(KEY_PATH, 'rb').read()
    f = Fernet(key)
    with open(TOKEN_PATH, 'rb') as f_enc:
        return pickle.loads(f.decrypt(f_enc.read()))

def authenticate():
    generate_key()
    creds = decrypt_token()
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
        creds = flow.run_local_server(port=0)
        encrypt_token(creds)
    return build('gmail', 'v1', credentials=creds)
