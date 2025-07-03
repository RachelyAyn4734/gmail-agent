# main.py
# ---------------------
import sys
from auth import authenticate
from rules import load_rules
from utils import setup_logger
from message_handler import process_message
from googleapiclient.errors import HttpError
from time import sleep

logger = setup_logger()

DEFAULT_LABELS = ['INBOX']

def get_messages(service, max_results=10, label_ids=None, days_back=10):
    from datetime import datetime, timedelta
    after_ts = int((datetime.utcnow() - timedelta(days=days_back)).timestamp())
    query = f"after:{after_ts} -in:sent -label:\"טופל על ידי סוכן\""
    try:
        res = service.users().messages().list(
            userId='me',
            q=query,
            labelIds=label_ids or None,
            maxResults=max_results,
            includeSpamTrash=False
        ).execute()
        msgs = res.get('messages', [])
        full_meta = []
        for m in msgs:
            try:
                meta = service.users().messages().get(userId='me', id=m['id'], format='metadata').execute()
                full_meta.append(meta)
            except HttpError as e:
                logger.warning(f"⚠ שגיאה בעת שליפת מטא-דאטה: {e}")
                sleep(2)
        full_meta.sort(key=lambda m: int(m['internalDate']), reverse=True)
        return [{'id': m['id']} for m in full_meta]
    except HttpError as e:
        logger.error(f"❌ שגיאה בבקשת רשימת מיילים: {e}")
        return []

def process_emails():
    service = authenticate()
    rules = load_rules()
    max_msgs = int(sys.argv[1]) if len(sys.argv) > 1 else rules.get('max_messages', 10)

    logger.info(f"🔍 סריקת עד {max_msgs} מיילים מה-INBOX")
    inbox_msgs = get_messages(service, max_results=max_msgs, label_ids=DEFAULT_LABELS)
    for msg in inbox_msgs:
        process_message(service, msg['id'], rules)

    logger.info(f"📂 סריקת עד {max_msgs} מיילים מה-SPAM")
    spam_msgs = get_messages(service, max_results=max_msgs, label_ids=['SPAM'], days_back=30)
    for msg in spam_msgs:
        process_message(service, msg['id'], rules)

    logger.info("✅ הסתיימה הסריקה")

if __name__ == '__main__':
    process_emails()
