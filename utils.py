import logging
import os

def setup_logger(name='gmail_agent', log_dir='logs'):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'agent.log')
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(name)
    
def clean_filename(s):
    return re.sub(r'[\\/*?:"<>|]', '_', s.strip())