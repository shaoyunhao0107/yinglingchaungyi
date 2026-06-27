# -*- coding: utf-8 -*-
# Probe Monica for valid bot_uid values by replaying the exact request the proxy makes
# (POST https://api.monica.im/api/custom_bot/chat with just the cookie + JSON body).
# Classifies each candidate as LIVE / OFFLINE / ERROR so we know what to map.
import json, re, ssl, time, uuid, urllib.request, urllib.error

_cfg = open('config.yaml', 'r', encoding='utf-8').read()
_m = re.search(r'cookie:\s*"(.*?)"', _cfg)
COOKIE = _m.group(1) if _m else ''
assert COOKIE, 'cookie not found in config.yaml'
URL = 'https://api.monica.im/api/custom_bot/chat'

# (display_name, candidate_bot_uid, use_model)
CANDIDATES = [
    # --- sweep #6: retry GPT-5.4 Pro with longer timeout ---
    ('GPT-5.4 Pro', 'gpt_5_4_pro', ''),
    ('GPT-5.4 Pro retry', 'gpt_5_4_pro', ''),
]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def build_body(bot_uid, model):
    conv = f'conv:{uuid.uuid4()}'
    welcome = f'msg:{uuid.uuid4()}'
    q = f'msg:{uuid.uuid4()}'
    return {
        'task_uid': f'task:{uuid.uuid4()}',
        'bot_uid': bot_uid,
        'data': {
            'conversation_id': conv,
            'pre_parent_item_id': q,
            'items': [
                {'conversation_id': conv, 'item_id': welcome, 'item_type': 'reply',
                 'data': {'type': 'text', 'content': '__RENDER_BOT_WELCOME_MSG__'}},
                {'conversation_id': conv, 'item_id': q, 'parent_item_id': welcome,
                 'item_type': 'question',
                 'data': {'type': 'text', 'content': 'hi', 'is_incognito': True}},
            ],
            'trigger_by': 'auto', 'use_model': model,
            'is_incognito': True, 'use_new_memory': False,
        },
        'language': 'auto', 'task_type': 'chat',
        'tool_data': {'sys_skill_list': []},
    }

def probe(bot_uid, model):
    body = json.dumps(build_body(bot_uid, model)).encode('utf-8')
    req = urllib.request.Request(URL, data=body, method='POST')
    req.add_header('Content-Type', 'application/json')
    req.add_header('Cookie', COOKIE)
    text = ''
    err = None
    try:
        with urllib.request.urlopen(req, timeout=90, context=CTX) as resp:
            for raw in resp:
                line = raw.decode('utf-8', 'ignore').strip()
                if not line.startswith('data:'):
                    continue
                payload = line[5:].strip()
                if payload == '[DONE]':
                    break
                try:
                    obj = json.loads(payload)
                except Exception:
                    continue
                if isinstance(obj.get('error'), dict) and obj['error'].get('msg'):
                    err = obj['error']['msg']
                text += obj.get('text', '')
                if len(text) > 200:
                    break
    except urllib.error.HTTPError as e:
        return 'HTTP_%d' % e.code, (e.read()[:160].decode('utf-8', 'ignore'))
    except Exception as e:
        return 'EXC', str(e)[:160]

    blob = (text + (err or ''))
    if '下线' in blob or '不可用' in blob or '不再可用' in blob:
        return 'OFFLINE', text[:80].replace('\n', ' ')
    if err:
        return 'ERROR', err[:120]
    if text.strip():
        return 'LIVE', text[:80].replace('\n', ' ')
    return 'EMPTY', ''

print('%-26s %-26s %-9s %s' % ('display', 'bot_uid', 'verdict', 'sample'))
print('-' * 100)
def safe(s):
    return s.encode('ascii', 'replace').decode('ascii')

for name, uid, model in CANDIDATES:
    verdict, sample = probe(uid, model)
    print('%-26s %-26s %-9s %s' % (name, uid, verdict, safe(sample)), flush=True)
    time.sleep(1.2)
