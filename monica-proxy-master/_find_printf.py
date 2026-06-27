p = r'G:\AI\monica\monica-proxy-master\internal\monica\sse.go'
lines = open(p, 'r', encoding='utf-8').readlines()
for i, l in enumerate(lines):
    if 'fmt.Printf' in l:
        print(i+1, ':', l.rstrip())
