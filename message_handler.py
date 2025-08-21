
# message_handler.py
# ---------------------
import os
import base64
from typing import List
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import Resource
from utils import clean_filename
import logging
from ai_agent import AIClassifier


logger = logging.getLogger('gmail_agent')

def extract_body(payload) -> str:
    if 'data' in payload.get('body', {}):
        return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
    if 'parts' in payload:
        for part in payload['parts']:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                return base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
    return ""

def classify_email(subject: str, body: str, sender: str, attachments: List[str], rules: dict) -> str:
    contents = f"{subject} {body} {sender}".lower()
    for word in rules.get('preserve_keywords', []):
        if word.lower() in contents:
            return 'preserve'
    for word in rules.get('promo_keywords', []):
        if word.lower() in contents:
            return 'promo'
    for email, words in rules.get('forward_keywords', {}).items():
        for word in words:
            if word.lower() in contents:
                return f'forward:{email}'
    if attachments and any(att.lower().endswith(('.jpg', '.png')) for att in attachments):
        return 'family_photos'
    return 'other'

def save_invoice_pdfs(service: Resource, msg_id: str, payload: dict, subject: str, body_plain: str, dst_folder="invoicesFromGmail/") -> int:
    if "חשבונית" not in subject and "חשבונית" not in body_plain:
        return 0
    parts = payload.get('parts', [])
    pdf_parts = [
        p for p in parts
        if (p.get('filename', '').lower().endswith('.pdf') or p.get('mimeType') == 'application/pdf')
        and 'attachmentId' in p.get('body', {})
    ]
    if not pdf_parts:
        return 0
    os.makedirs(dst_folder, exist_ok=True)
    clean_subject = clean_filename(subject)
    for idx, part in enumerate(pdf_parts, start=1):
        att_id = part['body']['attachmentId']
        att = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
        data = base64.urlsafe_b64decode(att['data'].encode('utf-8'))
        filename = f"{clean_subject}.pdf" if len(pdf_parts) == 1 else f"{clean_subject}_{idx}.pdf"
        fpath = os.path.join(dst_folder, filename)
        with open(fpath, 'wb') as f:
            f.write(data)
        logger.info(f"🧾 נשמרה חשבונית: {fpath}")
    return 1

def download_attachments(service: Resource, msg_id: str, payload: dict, save_path='downloads/') -> None:
    os.makedirs(save_path, exist_ok=True)
    parts = payload.get('parts', [])
    for part in parts:
        if part.get('filename') and part.get('body') and 'attachmentId' in part['body']:
            att_id = part['body']['attachmentId']
            att = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
            data = base64.urlsafe_b64decode(att['data'].encode('UTF-8'))
            with open(os.path.join(save_path, part['filename']), 'wb') as f:
                f.write(data)
            logger.info(f"✓ קובץ נשמר: {part['filename']}")

def move_to_trash(service: Resource, msg_id: str):
    service.users().messages().trash(userId='me', id=msg_id).execute()
    logger.info(f"🗑 מייל הועבר לאשפה (ID: {msg_id})")

def forward_email(service: Resource, msg_id: str, payload: dict, to_email: str):
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
    logger.info(f"📤 מייל הועבר ל-{to_email} (ID: {msg_id})")

def add_label(service: Resource, msg_id: str, label_name="טופל על ידי סוכן"):
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
    logger.info(f"🏷 נוספה תווית '{label_name}' למייל {msg_id}")

def process_message(service: Resource, msg_id: str, rules: dict):
    classifier = AIClassifier()
    msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
    payload = msg['payload']
    headers = {h['name']: h['value'] for h in payload.get('headers', [])}
    subject = headers.get('Subject', '')
    sender = headers.get('From', '')
    body_plain = extract_body(payload)
    attachments = [p['filename'] for p in payload.get('parts', []) if p.get('filename')]

    if save_invoice_pdfs(service, msg_id, payload, subject, body_plain):
        add_label(service, msg_id)
        move_to_trash(service, msg_id)
        return

    classification = classify_email(subject, body_plain, sender, attachments, rules)
    
    if classification == 'other':  # ברירת מחדל – תני ל-GPT לעזור
        classification = classifier.classify_email(subject, body_plain)

    logger.info(f"📧 מייל: '{subject}' → סיווג: {classification}")

    if classification == 'preserve':
        add_label(service, msg_id)
    elif classification == 'promo':
        move_to_trash(service, msg_id)
        add_label(service, msg_id)
    elif classification == 'family_photos':
        download_attachments(service, msg_id, payload)
        add_label(service, msg_id)
        move_to_trash(service, msg_id)
    elif classification.startswith('forward:'):
        to_email = classification.split(':', 1)[1]
        forward_email(service, msg_id, payload, to_email)
        add_label(service, msg_id)
        move_to_trash(service, msg_id)
