import tkinter as tk
from tkinter import messagebox, simpledialog
import json, shutil, os, subprocess

RULES_PATH = 'rules.json'
BACKUP_PATH = 'rules_backup.json'
AGENT_SCRIPT = 'SmartGmailAgent.py'

# ---------------- utils -----------------

def load_rules():
    if not os.path.exists(RULES_PATH):
        with open(RULES_PATH, 'w', encoding='utf-8') as f:
            json.dump({
                "promo_keywords": [],
                "preserve_keywords": [],
                "forward_keywords": {},
                "max_messages": 10
            }, f, ensure_ascii=False, indent=2)
    with open(RULES_PATH, encoding='utf-8') as f:
        return json.load(f)

def save_rules(data):
    shutil.copy(RULES_PATH, BACKUP_PATH)
    with open(RULES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# -------------- basic keywords (promo / preserve) -------------

def add_basic_keyword(category):
    word = simpledialog.askstring('מילה חדשה', f'מילה ל-{category}:')
    if not word:
        return
    for w in {word.strip(), word.strip()[::-1]}:
        if w and w not in rules[category]:
            rules[category].append(w)
    save_rules(rules); refresh()

def del_basic_keyword(listbox, category):
    sel = listbox.curselection()
    if not sel:
        return
    w = listbox.get(sel[0])
    rev = w[::-1]
    rules[category] = [x for x in rules[category] if x not in {w, rev}]
    save_rules(rules); refresh()

# -------------- forward dictionary -------------

def add_forward():
    email = simpledialog.askstring('כתובת יעד', 'הקלד כתובת מייל:')
    if not email:
        return
    word = simpledialog.askstring('מילת מפתח', 'הקלד מילת מפתח:')
    if not word:
        return
    rules.setdefault('forward_keywords', {}).setdefault(email, [])
    for w in {word.strip(), word.strip()[::-1]}:
        if w and w not in rules['forward_keywords'][email]:
            rules['forward_keywords'][email].append(w)
    save_rules(rules); refresh()

def del_forward():
    sel = forward_list.curselection()
    if not sel:
        return
    entry = forward_list.get(sel[0])  # format email >> word
    email, word = entry.split(' >> ', 1)
    rev = word[::-1]
    rules['forward_keywords'][email] = [w for w in rules['forward_keywords'][email] if w not in {word, rev}]
    if not rules['forward_keywords'][email]:
        del rules['forward_keywords'][email]
    save_rules(rules); refresh()

# -------------- misc -------------

def save_max():
    try:
        val = int(max_entry.get())
        rules['max_messages'] = val
        save_rules(rules)
    except ValueError:
        messagebox.showerror('שגיאה', 'הכנס מספר')

def run_agent():
    subprocess.Popen(['python', AGENT_SCRIPT])
    messagebox.showinfo('הופעל', 'הסוכן הופעל!')

# -------------- refresh lists -------------

def refresh():
    promo_list.delete(0, tk.END)
    for w in sorted(set(rules['promo_keywords'])):
        promo_list.insert(tk.END, w)
    preserve_list.delete(0, tk.END)
    for w in sorted(set(rules['preserve_keywords'])):
        preserve_list.insert(tk.END, w)
    forward_list.delete(0, tk.END)
    for email, words in rules.get('forward_keywords', {}).items():
        for w in sorted(set(words)):
            forward_list.insert(tk.END, f'{email} >> {w}')
    max_entry.delete(0, tk.END)
    max_entry.insert(0, str(rules.get('max_messages', 10)))

# ---------------- GUI build -----------------

rules = load_rules()
root = tk.Tk(); root.title('Gmail Agent UI')

# promo
tk.Label(root, text='מילות פרסומת').grid(row=0, column=0)
promo_list = tk.Listbox(root, height=7, width=30); promo_list.grid(row=1, column=0)
tk.Button(root, text='➕', command=lambda: add_basic_keyword('promo_keywords')).grid(row=2, column=0, sticky='we')
tk.Button(root, text='🗑', command=lambda: del_basic_keyword(promo_list, 'promo_keywords')).grid(row=3, column=0, sticky='we')

# preserve
tk.Label(root, text='מילים למניעת מחיקה').grid(row=0, column=1)
preserve_list = tk.Listbox(root, height=7, width=30); preserve_list.grid(row=1, column=1)
tk.Button(root, text='➕', command=lambda: add_basic_keyword('preserve_keywords')).grid(row=2, column=1, sticky='we')
tk.Button(root, text='🗑', command=lambda: del_basic_keyword(preserve_list, 'preserve_keywords')).grid(row=3, column=1, sticky='we')

# forward dict
tk.Label(root, text='כללי העברה (email >> word)').grid(row=4, column=0, columnspan=2)
forward_list = tk.Listbox(root, height=8, width=60); forward_list.grid(row=5, column=0, columnspan=2)
tk.Button(root, text='➕ כלל חדש', command=add_forward).grid(row=6, column=0, sticky='we')
tk.Button(root, text='🗑 מחק כלל', command=del_forward).grid(row=6, column=1, sticky='we')

# misc bottom
tk.Label(root, text='כמות מיילים לסריקה').grid(row=7, column=0)
max_entry = tk.Entry(root, width=10); max_entry.grid(row=7, column=1, sticky='w')
tk.Button(root, text='שמור', command=save_max).grid(row=7, column=1, sticky='e')
tk.Button(root, text='🚀 הפעל סוכן', command=run_agent).grid(row=8, column=0, columnspan=2, pady=10)

refresh()
root.mainloop()
