
import json
import os
import subprocess

BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '368933843').split(',') if x.strip()]
DESCRIPTIONS = {
    '': ('Start or restart the bot', 'Change language', 'Cancel the current operation', 'Manage country prices', 'Open the admin panel'),
    'fa': ('شروع یا شروع دوباره ربات', 'تغییر زبان', 'لغو عملیات جاری', 'مدیریت قیمت کشورها', 'پنل مدیریت'),
    'en': ('Start or restart the bot', 'Change language', 'Cancel the current operation', 'Manage country prices', 'Open the admin panel'),
    'ru': ('Запустить бота заново', 'Изменить язык', 'Отменить текущее действие', 'Управление ценами по странам', 'Панель администратора'),
    'zh': ('启动或重新启动机器人', '更改语言', '取消当前操作', '管理各国价格', '打开管理面板'),
    'ar': ('بدء البوت أو إعادة تشغيله', 'تغيير اللغة', 'إلغاء العملية الحالية', 'إدارة أسعار الدول', 'فتح لوحة الإدارة'),
}


def call(method, payload):
    if not BOT_TOKEN:
        raise RuntimeError('BOT_TOKEN is required')
                                                                             
                                                                        
    config = 'url = "https://api.telegram.org/bot' + BOT_TOKEN + '/' + method + '"\n'
    response = subprocess.run(
        ['curl', '-4', '--silent', '--show-error', '--max-time', '20', '--config', '-',
         '-H', 'Content-Type: application/json', '--data-binary', json.dumps(payload)],
        input=config, text=True, capture_output=True, timeout=25)
    if response.returncode:
        raise RuntimeError('Telegram API transport failed for ' + method)
    result = json.loads(response.stdout)
    if not result.get('ok'):
        raise RuntimeError('Telegram rejected ' + method + ': ' + result.get('description', 'unknown error'))
    return result['result']


def configure(scope, language, admin=False):
    desc = DESCRIPTIONS[language]
    names = ['start', 'language', 'cancel'] + (['price', 'panel'] if admin else [])
    commands = [dict(command=name, description=desc[i]) for i, name in enumerate(names)]
    args = dict(scope=scope, language_code=language)
    call('setMyCommands', dict(args, commands=commands))
    actual = call('getMyCommands', args)
    if actual != commands:
        raise RuntimeError('Command menu verification failed: ' + repr(args))
    print(('admin' if admin else 'default') + ' ' + (language or 'fallback') + ': ' + ', '.join(names))


def main():
    for language in DESCRIPTIONS:
        for scope in ({'type': 'default'}, {'type': 'all_private_chats'}):
            configure(scope, language)
    pending = []
    for admin_id in ADMIN_IDS:
        for language in DESCRIPTIONS:
            try:
                configure({'type': 'chat', 'chat_id': admin_id}, language, admin=True)
            except RuntimeError as exc:
                if 'chat not found' in str(exc).lower() or 'user not found' in str(exc).lower():
                    pending.append(admin_id)
                    print('Pending admin ' + str(admin_id) + ': open the bot and send /start.')
                    break
                raise
    print('Available command menus saved and verified.')
    if pending:
        print('Pending admin menus will be configured by the bot on /start: ' + ', '.join(map(str, pending)))


if __name__ == '__main__':
    main()
