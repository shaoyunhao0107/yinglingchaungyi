import re

p = r'G:\AI\monica\monica-proxy-master\internal\monica\sse.go'
with open(p, 'r', encoding='utf-8') as f:
    lines = f.readlines()

result = []
for i, l in enumerate(lines):
    if 'fmt.Printf' in l:
        print(f'FOUND line {i+1}: {l.rstrip()}')
    else:
        result.append(l)

print(f'Original: {len(lines)} lines, After: {len(result)} lines')
