import re, sys

p = r'G:\AI\monica\monica-proxy-master\config.yaml'

new_cookie = (
    '_fbp=fb.1.1739176855648.69779105623515813; '
    '_fwb=105eHpTBhhr9DPJYRuFEniO.1739176854710; '
    '_ga=GA1.1.750584991.1739176856; '
    '_gcl_au=1.1.511971793.1771050140; '
    '_rdt_uuid=1770798193593.19b85d1c-0d25-4c38-9b61-308052c21029; '
    '_twpid=tw.1772505786724.392101319543868113; '
    'session_id=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3NzIxNjE0MTYsImlzcyI6Im1vbmljYSIsInVzZXJfaWQiOjc2ODQ5MDkyLCJ1c2VyX25hbWUiOiJcdTVmMjBcdTRlM2RcdTYwMWQiLCJqdGkiOiI0MGRlYjI5ZGYxZWM0ZmFiOTgxM2FiODEyZmYwMzFiNSIsImNsaWVudF90eXBlIjoid2ViIn0.96mvn7rsxq1nFD4kjxWUnoc4jMJH3OjoNANq-kqFdLc; '
    '_clck=68dws7%5E2%5Eg4m%5E0%5E1867; '
    '_ga_E249CNSDCV=GS2.1.s1774361517$o361$g1$t1774361523$j54$l0$h0; '
    '_uetsid=6eed6730278b11f1b30673ddaac77a08; '
    '_ga_JDZPETSM4F=GS2.1.s1774361517$o639$g1$t1774361541$j36$l0$h0; '
    '_ga_RJYZXDEM8N=GS2.1.s1774361517$o639$g1$t1774361541$j36$l0$h79800091; '
    '_clsk=1t4rn4e%5E1774361543719%5E3%5E0%5Ej.clarity.ms%2Fcollect'
)

with open(p, 'r', encoding='utf-8') as f:
    content = f.read()

new_content = re.sub(
    r'(?s)(monica:\n  cookie: ").*?(")',
    lambda m: m.group(1) + new_cookie + '"',
    content
)

if new_content == content:
    print('NO CHANGE - pattern not matched')
    sys.exit(1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('OK - cookie updated')
