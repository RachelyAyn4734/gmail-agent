import json

def load_rules(path='rules.json'):
    with open(path, encoding='utf-8') as f:
        return json.load(f)
