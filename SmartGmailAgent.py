import os
import pickle
import base64
import re
import json
import sys
import mimetypes
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']

with open('rules.json', encoding='utf-8') as f:
    RULES = json.load(f)

def authenticate_gmail():
    creds = None
    if os.path.exists('token.pkl'):
        with open('token.pkl', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.pkl', 'wb') as token:
            pickle.dump(creds, token)
    return build('gmail', 'v1', credentials=creds)


def get_messages(service, max_results=10, label_ids=None, days_back=10):
    # 1. שאילתה – אחרי X ימים, לא נגעו ע"י הסוכן, לא בתיקיית נשלח
    after_ts = int((datetime.utcnow() - timedelta(days=days_back)).timestamp())
    query = f"after:{after_ts} -in:sent -label:\"טופל על ידי סוכן\""

    # 2. קריאה ל-API, כולל labelIds
    res = service.users().messages().list(
        userId='me',
        q=query,
        labelIds=label_ids or None,        # ← נוספה השורה
        maxResults=max_results,
        includeSpamTrash=False
    ).execute()

    msgs = res.get('messages', [])

    # 3. מיון מקומי לפי internalDate מהחדש לישן
    full_meta = [
        service.users().messages().get(userId='me', id=m['id'],
                                       format='metadata').execute()
        for m in msgs
    ]
    full_meta.sort(key=lambda m: int(m['internalDate']), reverse=True)
    return [ {'id': m['id']} for m in full_meta ]


def clean_filename(s):
    """הסר תווים לא חוקיים לשם קובץ"""
    return re.sub(r'[\\/*?:"<>|]', '_', s.strip())

def save_invoice_pdfs(service, msg_id, dst_folder="invoicesFromGmail/"):
    """
    שומר קובצי PDF ממייל שמכיל את המילה "חשבונית"
    ושומר את הקובץ בשם נושא המייל.

    :return: 1 אם נשמר לפחות PDF אחד, אחרת 0
    """
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    
    headers = {h['name']: h['value'] for h in payload.get('headers', [])}
    subject = headers.get('Subject', '')
    body_plain = extract_body(payload)

    if "חשבונית" not in subject and "חשבונית" not in body_plain:
        return 0  # אין מילה "חשבונית" – לא נמשיך

    parts = payload.get('parts', [])
    pdf_parts = [
        p for p in parts
        if (
            p.get('filename', '').lower().endswith('.pdf')
            or p.get('mimeType') == 'application/pdf'
        )
        and 'attachmentId' in p.get('body', {})
    ]

    if not pdf_parts:
        return 0  # אין PDF

    os.makedirs(dst_folder, exist_ok=True)

    clean_subject = clean_filename(subject)
    for idx, part in enumerate(pdf_parts, start=1):
        att_id = part['body']['attachmentId']
        att = service.users().messages().attachments().get(
            userId='me', messageId=msg_id, id=att_id).execute()
        data = base64.urlsafe_b64decode(att['data'].encode('utf-8'))

        # במידה ויש יותר מ-PDF אחד עם אותו שם נושא, הוסף אינדקס
        filename = f"{clean_subject}.pdf" if len(pdf_parts) == 1 else f"{clean_subject}_{idx}.pdf"
        fpath = os.path.join(dst_folder, filename)

        with open(fpath, 'wb') as f:
            f.write(data)

        print(f"🧾 נשמרה חשבונית: {fpath}")

    return 1

  
def extract_body(payload):
    if 'data' in payload.get('body', {}):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
    return ""

def classify_email(subject, body, sender, attachments):
    body = body or ''
    subject = subject or ''
    sender = sender or ''
    contents = f"{subject} {body} {sender}".lower()
    
    # שמור מפני מחיקה
    for word in RULES.get('preserve_keywords', []):
        if word.lower() in contents:
            return 'preserve'

    # פרסומת
    for word in RULES.get('promo_keywords', []):
        if word.lower() in contents:
            return 'promo'

    # בדוק אם שייך להעברה
    for email, words in RULES.get('forward_keywords', {}).items():
        for word in words:
            if word.lower() in contents:
                return f'forward:{email}'

    # תמונה משפחתית
    if attachments and any(att.lower().endswith(('.jpg', '.png')) for att in attachments):
        return 'family_photos'

    return 'other'

def download_attachments(service, msg_id, save_path='downloads/'):
    os.makedirs(save_path, exist_ok=True)
    msg = service.users().messages().get(userId='me', id=msg_id).execute()
    parts = msg['payload'].get('parts', [])
    for part in parts:
        if part.get('filename') and part.get('body') and 'attachmentId' in part['body']:
            att_id = part['body']['attachmentId']
            att = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
            data = base64.urlsafe_b64decode(att['data'].encode('UTF-8'))
            with open(os.path.join(save_path, part['filename']), 'wb') as f:
                f.write(data)
            print(f"✓ קובץ נשמר: {part['filename']}")

def move_to_trash(service, msg_id):
    service.users().messages().trash(userId='me', id=msg_id).execute()
    print(f"🗑 מייל הועבר לאשפה (ID: {msg_id})")

def forward_email(service, msg_id, to_email):
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    headers = {h['name']: h['value'] for h in payload['headers']}
    subject = headers.get('Subject', '')
    sender = headers.get('From', '')
    body = extract_body(payload)

    message = MIMEMultipart()
    message['to'] = to_email
    message['from'] = 'me'
    message['subject'] = f"הועבר אוטומטית: {subject}"

    body_content = f"הודעה זו הועברה אוטומטית ממערכת Gmail Agent:\n\nנשלח במקור על ידי: {sender}\n\n{body}"
    message.attach(MIMEText(body_content, 'plain'))

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId='me', body={'raw': raw_message}).execute()
    print(f"📤 מייל הועבר בפועל ל-{to_email} (ID: {msg_id})")

def add_label(service, msg_id, label_name="טופל על ידי סוכן"):
    label_id = None
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['name'] == label_name:
            label_id = label['id']
            break

    if not label_id:
        label_obj = {'name': label_name, 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show'}
        new_label = service.users().labels().create(userId='me', body=label_obj).execute()
        label_id = new_label['id']

    service.users().messages().modify(userId='me', id=msg_id, body={'addLabelIds': [label_id]}).execute()
    print(f"🏷 נוספה תווית '{label_name}' למייל {msg_id}")

def process_message(service, msg_id):
    # שמירת חשבוניות (PDF + "חשבונית")
    if save_invoice_pdfs(service, msg_id):
       add_label(service, msg_id)
       move_to_trash(service, msg_id)
       return  
       
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    headers = {h['name']: h['value'] for h in msg['payload']['headers']}
    subject = headers.get('Subject', '')
    sender = headers.get('From', '')
    body = extract_body(msg['payload'])
    attachments = [p['filename'] for p in msg['payload'].get('parts', []) if p.get('filename')]

    classification = classify_email(subject, body, sender, attachments)
    print(f"📧 מייל: '{subject}' \n→ סיווג: {classification}")

    if classification == 'preserve':
        add_label(service, msg_id)
    elif classification == 'promo':
        move_to_trash(service, msg_id)
        add_label(service, msg_id)
    elif classification == 'family_photos':
        download_attachments(service, msg_id)
        add_label(service, msg_id)
        move_to_trash(service, msg_id)
    elif classification.startswith('forward:'):
        to_email = classification.split(':', 1)[1]
        forward_email(service, msg_id, to_email)
        add_label(service, msg_id)
        move_to_trash(service, msg_id)

def process_emails():
    service   = authenticate_gmail()
    max_msgs  = int(sys.argv[1]) if len(sys.argv) > 1 else RULES.get('max_messages', 10)

    # --- INBOX (חדש → ישן) ---
    inbox_msgs = get_messages(service, max_results=max_msgs,
                              label_ids=['INBOX'])
    for msg in inbox_msgs:
        process_message(service, msg['id'])
        

    # --- SPAM ---
    spam_msgs = get_messages(service, max_results=max_msgs,
                             label_ids=['SPAM'], days_back=30)
    for msg in spam_msgs:
        move_to_trash(service, msg['id'])
        add_label(service, msg['id'])

    print("\n✅ הסתיימה הסריקה")

if __name__ == '__main__':
    process_emails()
