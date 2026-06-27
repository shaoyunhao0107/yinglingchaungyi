import yaml
p = 'config.yaml'
d = yaml.safe_load(open(p, 'r', encoding='utf-8'))
cookie = d['monica']['cookie']
print('cookie_len=', len(cookie))
print('first_180=', cookie[:180])
print('has_old_uid72146500=', '72146500' in cookie)
print('has_new_uid76849092=', '76849092' in cookie)
print('token=', d['security']['bearer_token'])
