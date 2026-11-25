
from contextvars import ContextVar

LANGUAGE = ContextVar('seller_language', default='fa')
                                                                                
LANGUAGES = {'fa': '\u200e🇮🇷 \u200eفارسی', 'en': '\u200e🇬🇧 \u200eEnglish', 'ru': '\u200e🇷🇺 \u200eРусский', 'zh': '\u200e🇨🇳 \u200e中文', 'ar': '\u200e🇸🇦 \u200eالعربية'}
PICK_LANGUAGE = '🌐 زبان خود را انتخاب کنید\n\nChoose your language'
TEXT = {}


def add(key, fa, en, ru, zh, ar):
    TEXT[key] = dict(zip(LANGUAGES, (fa, en, ru, zh, ar)))


def tr(key, **kwargs):
    text = TEXT[key][LANGUAGE.get() if LANGUAGE.get() in LANGUAGES else 'fa']
    return text.format(**kwargs) if kwargs else text


add('welcome',
    '🚀 <b>فروش اکانت تلگرام</b> 💎\n\n👋 سلام {name}!\n🔥 اینجا می‌تونی اکانت تلگرامت رو سریع بفروشی.\n\n✨ یکی از گزینه‌های زیر رو انتخاب کن:',
    '🚀 <b>Sell your Telegram account</b> 💎\n\n👋 Hello {name}!\n🔥 You can sell your account quickly here.\n\n✨ Choose an option:',
    '🚀 <b>Продажа аккаунта Telegram</b> 💎\n\n👋 Здравствуйте, {name}!\n🔥 Здесь можно быстро продать аккаунт.\n\n✨ Выберите действие:',
    '🚀 <b>出售 Telegram 账号</b> 💎\n\n👋 你好，{name}！\n🔥 在这里可以快速出售你的账号。\n\n✨ 请选择：',
    '🚀 <b>بيع حساب Telegram</b> 💎\n\n👋 مرحبًا {name}!\n🔥 يمكنك بيع حسابك بسرعة هنا.\n\n✨ اختر خيارًا:')
add('friend', 'دوست عزیز', 'friend', 'друг', '朋友', 'صديقي')
add('sell', 'فروش اکانت', 'Sell account', 'Продать аккаунт', '出售账号', 'بيع الحساب')
add('info_btn', 'توضیحات', 'Information', 'Информация', '说明', 'معلومات')
add('my_info_btn', 'اطلاعات من', 'My information', 'Моя информация', '我的信息', 'معلوماتي')
add('support_btn', 'پشتیبانی', 'Support', 'Поддержка', '客服支持', 'الدعم')
add('countries_btn', 'لیست کشور ها', 'Country list', 'Список стран', '国家列表', 'قائمة الدول')
add('countries_closed', 'خرید کشورهای زیر در حال حاضر توسط ادمین بسته شده و نمی‌توانید اکانت‌های این کشورها را به فروش برسانید:', 'Purchases from the following countries are currently disabled by the admin, and you cannot sell accounts from these countries:', 'Покупка аккаунтов из следующих стран сейчас отключена администратором, поэтому вы не можете продать аккаунты этих стран:', '管理员目前已关闭购买以下国家的账号，您无法出售这些国家的账号：', 'أوقف المشرف حاليًا شراء الحسابات من الدول التالية، ولا يمكنك بيع حسابات هذه الدول:')
add('countries_open', 'خرید کشورهای زیر باز است و می‌توانید اکانت خود را به فروش برسانید:', 'Purchases from the following countries are enabled, and you can sell your account:', 'Покупка аккаунтов из следующих стран открыта, и вы можете продать свой аккаунт:', '已开放购买以下国家的账号，您可以出售自己的账号：', 'شراء الحسابات من الدول التالية متاح، ويمكنك بيع حسابك:')
add('countries_none', 'هیچ‌کدام', 'None', 'Нет', '无', 'لا توجد')
add('countries_price_note', 'توجه: برای فروش، قیمت کشور یا قیمت پیش‌فرض نیز باید تنظیم شده باشد.', 'Note: a country-specific or default price must also be set before a sale.', 'Примечание: для продажи также должна быть установлена цена страны или цена по умолчанию.', '注意：出售前还须设置该国家的价格或默认价格。', 'ملاحظة: يجب أيضاً تحديد سعر للدولة أو سعر افتراضي قبل البيع.')
add('support_prompt', 'لطفا پیام خود را برای پشتیبانی ارسال کنید. تیم پشتیبانی در اسرع وقت به پیام شما پاسخ خواهد داد.\n/cancel برای لغو', 'Please send your message to support. The support team will reply to you as soon as possible.\n/cancel to cancel', 'Пожалуйста, отправьте сообщение в поддержку. Служба поддержки ответит вам как можно скорее.\n/cancel — отмена', '请向客服发送您的消息。客服团队会尽快回复您。\n发送 /cancel 取消', 'يرجى إرسال رسالتك إلى الدعم. سيرد عليك فريق الدعم في أقرب وقت ممكن.\n/cancel للإلغاء')
add('support_received', '✅ پیام شما با موفقیت به تیم پشتیبانی ارسال شد.', '✅ Your message was successfully sent to the support team.', '✅ Ваше сообщение успешно отправлено в службу поддержки.', '✅ 您的消息已成功发送给客服团队。', '✅ تم إرسال رسالتك بنجاح إلى فريق الدعم.')
add('support_reply_header', '📨 <b>پاسخ پشتیبانی · تیکت #{id}</b>', '📨 <b>Support reply · ticket #{id}</b>', '📨 <b>Ответ поддержки · обращение #{id}</b>', '📨 <b>客服回复 · 工单 #{id}</b>', '📨 <b>رد الدعم · التذكرة #{id}</b>')
add('support_reply_btn', 'پاسخ به پشتیبانی', 'Reply to support', 'Ответить поддержке', '回复客服', 'الرد على الدعم')
add('support_busy', 'اول عملیات فعلی رو تموم کن یا /cancel رو بزن، بعد با پشتیبانی تماس بگیر.', 'Finish the current operation or send /cancel before contacting support.', 'Сначала завершите текущее действие или отправьте /cancel, затем напишите в поддержку.', '请先完成当前操作或发送 /cancel，再联系支持。', 'أكمل العملية الحالية أو أرسل /cancel قبل التواصل مع الدعم.')
add('support_cancelled', 'ارسال پیام به پشتیبانی لغو شد.', 'Support message cancelled.', 'Сообщение в поддержку отменено.', '已取消发送客服消息。', 'تم إلغاء رسالة الدعم.')
add('unknown_date', 'نامشخص', 'Unknown', 'Неизвестно', '未知', 'غير معروف')
add('my_info',
    '🙂 <b>اطلاعات من</b>\n\n🔑 شناسه کاربری: <code>{user_id}</code>\n🗓 اولین شروع: {started}\n📞 تعداد شماره‌های فروخته‌شده: {sold}\n💰 موجودی: {balance}\n🪙 مجموع برداشت: {withdrawn}\n\nپرداخت‌ها توسط ادمین به‌صورت دستی انجام می‌شوند.',
    '🙂 <b>My information</b>\n\n🔑 User ID: <code>{user_id}</code>\n🗓 First start: {started}\n📞 Numbers sold: {sold}\n💰 Available balance: {balance}\n🪙 Total withdrawn: {withdrawn}\n\nPayments are made manually by the admin.',
    '🙂 <b>Моя информация</b>\n\n🔑 ID пользователя: <code>{user_id}</code>\n🗓 Первый запуск: {started}\n📞 Продано номеров: {sold}\n💰 Доступный баланс: {balance}\n🪙 Всего выведено: {withdrawn}\n\nВыплаты выполняет администратор вручную.',
    '🙂 <b>我的信息</b>\n\n🔑 用户 ID：<code>{user_id}</code>\n🗓 首次启动：{started}\n📞 已出售号码：{sold}\n💰 可用余额：{balance}\n🪙 已提现总额：{withdrawn}\n\n由管理员手动付款。',
    '🙂 <b>معلوماتي</b>\n\n🔑 معرف المستخدم: <code>{user_id}</code>\n🗓 أول بدء: {started}\n📞 الأرقام المباعة: {sold}\n💰 الرصيد المتاح: {balance}\n🪙 إجمالي المسحوبات: {withdrawn}\n\nيُجري المشرف المدفوعات يدويًا.')
add('back', 'بازگشت', 'Back', 'Назад', '返回', 'رجوع')
add('cancel_btn', 'انصراف', 'Cancel', 'Отмена', '取消', 'إلغاء')
add('confirm', 'تایید', 'Confirm', 'Подтвердить', '确认', 'تأكيد')
add('logged_out', 'لاگ اوت کردم', 'I logged out', 'Я вышел', '我已退出', 'سجّلت الخروج')
add('info',
    '💡 <b>توضیحات</b>\n\n1️⃣ روی «فروش اکانت» بزن.\n2️⃣ شماره اکانت رو با کد کشور بفرست.\n3️⃣ کدی که تلگرام می‌فرسته رو وارد کن و «تایید» رو بزن.\n4️⃣ اگر اکانت رمز دو مرحله‌ای داره، رمز رو بفرست.\n5️⃣ دستگاه های دیگه روی اکانت رو خارج کن و دکمه «لاگ اوت کردم» رو بزن\n\n❗️ اکانت باید روی دستگاه خودت وارد باشه تا کد رو ببینی.',
    '💡 <b>How it works</b>\n\n1️⃣ Tap “Sell account”.\n2️⃣ Send the phone number with country code.\n3️⃣ Enter the code from Telegram and tap “Confirm”.\n4️⃣ If prompted, send your 2FA password.\n5️⃣ Log out the other devices on the account and tap “I logged out”.\n\n❗️Keep your account logged in on your device to receive the code.',
    '💡 <b>Как это работает</b>\n\n1️⃣ Нажмите «Продать аккаунт».\n2️⃣ Отправьте номер с кодом страны.\n3️⃣ Введите код Telegram и нажмите «Подтвердить».\n4️⃣ При запросе отправьте пароль 2FA.\n5️⃣ Выйдите с других устройств аккаунта и нажмите «Я вышел».\n\n❗️Аккаунт должен быть открыт на вашем устройстве, чтобы получить код.',
    '💡 <b>使用说明</b>\n\n1️⃣ 点击“出售账号”。\n2️⃣ 发送带国家区号的手机号。\n3️⃣ 输入 Telegram 验证码并点击“确认”。\n4️⃣ 如有提示，请发送两步验证密码。\n5️⃣ 退出该账号上的其他设备，然后点击“我已退出”。\n\n❗️请在自己的设备上保持登录，以便接收验证码。',
    '💡 <b>طريقة الاستخدام</b>\n\n1️⃣ اضغط «بيع الحساب».\n2️⃣ أرسل الرقم مع رمز الدولة.\n3️⃣ أدخل رمز Telegram واضغط «تأكيد».\n4️⃣ أرسل كلمة مرور التحقق بخطوتين إذا طُلبت.\n5️⃣ سجّل الخروج من الأجهزة الأخرى على الحساب واضغط «سجّلت الخروج».\n\n❗️احتفظ بتسجيل الدخول على جهازك لاستلام الرمز.')
add('ask_phone',
    '📞 شماره اکانتی که می‌خوای بفروشی رو با کد کشور بفرست:\nمثال:\n<code>+12025550123</code>\n\n❌ برای لغو /cancel رو بزن.',
    '📞 Send the account phone number with country code:\nExample:\n<code>+12025550123</code>\n\n❌ Send /cancel to cancel.',
    '📞 Отправьте номер аккаунта с кодом страны:\nНапример:\n<code>+12025550123</code>\n\n❌ /cancel — отмена.',
    '📞 请发送带国家区号的账号手机号：\n例如：\n<code>+12025550123</code>\n\n❌ 发送 /cancel 取消。',
    '📞 أرسل رقم الحساب مع رمز الدولة:\nمثال:\n<code>+12025550123</code>\n\n❌ أرسل /cancel للإلغاء.')
add('ask_2fa',
    '🔒 این اکانت رمز دو مرحله‌ای (2FA) داره.\n🔑 رمز دو مرحله‌ایش رو بفرست.',
    '🔒 This account has two-step verification (2FA).\n🔑 Send its password.',
    '🔒 Включена двухэтапная проверка (2FA).\n🔑 Отправьте пароль.',
    '🔒 此账号启用了两步验证 (2FA)。\n🔑 请发送密码。',
    '🔒 التحقق بخطوتين (2FA) مفعّل.\n🔑 أرسل كلمة المرور.')
add('wrong_2fa', '❌ رمز دو مرحله‌ای اشتباهه. دوباره بفرست یا /cancel بزن.',
    '❌ Incorrect 2FA password. Try again or send /cancel.', '❌ Неверный пароль 2FA. Повторите или отправьте /cancel.',
    '❌ 两步验证密码错误，请重试或发送 /cancel。', '❌ كلمة مرور التحقق بخطوتين غير صحيحة. حاول مجددًا أو أرسل /cancel.')
add('code_prefix',
    '{flag} کد ارسال‌شده به شماره {phone} رو با کیبورد زیر وارد کن:\n\n🔐 کد:\n{code}\n\n⌛️ توجه داشته باشید کد های تلگرام بعد از چند دقیقه منقضی میشن',
    '{flag} Enter the code sent to {phone} using the keypad below:\n\n🔐 Code:\n{code}\n\n⌛️ Telegram codes expire after a few minutes',
    '{flag} Введите код, отправленный на {phone}, с помощью клавиатуры ниже:\n\n🔐 Код:\n{code}\n\n⌛️ Коды Telegram истекают через несколько минут',
    '{flag} 使用下方键盘输入发送至 {phone} 的验证码：\n\n🔐 验证码：\n{code}\n\n⌛️ Telegram 验证码几分钟后过期',
    '{flag} أدخل الرمز المرسل إلى {phone} باستخدام لوحة المفاتيح أدناه:\n\n🔐 الرمز:\n{code}\n\n⌛️ تنتهي صلاحية رموز Telegram بعد دقائق')
add('success',
    '🎉 <b>فروش با موفقیت تأیید شد</b> 🆗\n\n📞 اکانت <code>{phone}</code> ثبت شد.\n🔑 شماره ثبت: <b>#{acc}</b>\n🚀 برای فروش اکانت بعدی /start رو بزن.',
    '🎉 <b>Sale confirmed</b> 🆗\n\n📞 Account <code>{phone}</code> registered.\n🔑 Reference: <b>#{acc}</b>\n🚀 Send /start to sell another account.',
    '🎉 <b>Продажа подтверждена</b> 🆗\n\n📞 Аккаунт <code>{phone}</code> зарегистрирован.\n🔑 Номер: <b>#{acc}</b>\n🚀 /start — продать другой аккаунт.',
    '🎉 <b>出售已确认</b> 🆗\n\n📞 账号 <code>{phone}</code> 已登记。\n🔑 编号：<b>#{acc}</b>\n🚀 发送 /start 出售另一个账号。',
    '🎉 <b>تم تأكيد البيع</b> 🆗\n\n📞 تم تسجيل الحساب <code>{phone}</code>.\n🔑 المرجع: <b>#{acc}</b>\n🚀 أرسل /start لبيع حساب آخر.')
add('cancelled', '🚫 لغو شد. /start برای شروع دوباره.', '🚫 Cancelled. Send /start to begin again.', '🚫 Отменено. /start — начать заново.', '🚫 已取消。发送 /start 重新开始。', '🚫 تم الإلغاء. أرسل /start للبدء مجددًا.')
add('invalid_phone', '❌ شماره معتبر نیست.\nمثال: <code>+12025550123</code>', '❌ Invalid phone number.\nExample: <code>+12025550123</code>', '❌ Неверный номер.\nНапример: <code>+12025550123</code>', '❌ 手机号无效。\n例如：<code>+12025550123</code>', '❌ رقم غير صالح.\nمثال: <code>+12025550123</code>')
add('retry_phone', '❌ شماره‌ی وارد‌شده معتبر نیست. دوباره بفرست یا /cancel بزن.', '❌ Invalid phone number. Try again or send /cancel.', '❌ Неверный номер. Повторите или отправьте /cancel.', '❌ 手机号无效，请重试或发送 /cancel。', '❌ الرقم غير صالح. حاول مجددًا أو أرسل /cancel.')
add('unregistered_phone', '❌ این شماره روی تلگرام ثبت نشده است.', '❌ This number is not registered on Telegram.', '❌ Этот номер не зарегистрирован в Telegram.', '❌ 此号码未注册 Telegram。', '❌ هذا الرقم غير مسجل في Telegram.')
add('generic_error', '❌ خطایی رخ داد. /start رو بزن و دوباره تلاش کن.', '❌ Something went wrong. Send /start and try again.', '❌ Произошла ошибка. Отправьте /start и повторите.', '❌ 出错了。请发送 /start 重试。', '❌ حدث خطأ. أرسل /start وحاول مجددًا.')
add('phone_flood', '⏳ تلگرام روی این شماره محدودیت گذاشته.\n{m} دقیقه دیگه دوباره تلاش کن.', '⏳ Telegram rate limit.\nTry again in {m} minutes.', '⏳ Ограничение Telegram.\nПовторите через {m} мин.', '⏳ Telegram 频率限制。\n请在 {m} 分钟后重试。', '⏳ تقييد من Telegram.\nحاول مجددًا بعد {m} دقيقة.')
add('step_expired', 'این مرحله منقضی شده. /start', 'This step has expired. /start', 'Этот шаг устарел. /start', '此步骤已过期。/start', 'انتهت صلاحية هذه الخطوة. /start')
add('needs_password', 'این اکانت رمز داره؛ رمز رو به صورت متن بفرست.', 'This account requires a password. Send it as text.', 'Нужен пароль. Отправьте его текстом.', '此账号需要密码，请以文本发送。', 'هذا الحساب يتطلب كلمة مرور. أرسلها كنص.')
add('incomplete_code', 'کد ناقصه', 'The code is incomplete', 'Код неполный', '验证码不完整', 'الرمز غير مكتمل')
add('checking_code', '⌛️ در حال بررسی کد...', '⌛️ Checking code...', '⌛️ Проверяем код...', '⌛️ 正在验证验证码…', '⌛️ جارٍ التحقق من الرمز...')
add('code_too_long', 'کد حداکثر ۶ رقمه', 'The code can have at most 6 digits', 'В коде не более 6 цифр', '验证码最多 6 位', 'الرمز بحد أقصى 6 أرقام')
add('wrong_code', '❌ کد اشتباه بود. دوباره وارد کن:\n\n', '❌ Incorrect code. Enter it again:\n\n', '❌ Неверный код. Введите ещё раз:\n\n', '❌ 验证码错误，请重新输入：\n\n', '❌ الرمز غير صحيح. أدخله مجددًا:\n\n')
add('code_expired', '⌛️ کد منقضی شد. /start رو بزن و دوباره شماره رو بفرست.', '⌛️ Code expired. Send /start and enter the number again.', '⌛️ Код истёк. Отправьте /start и введите номер заново.', '⌛️ 验证码已过期。请发送 /start 并重新输入号码。', '⌛️ انتهت صلاحية الرمز. أرسل /start وأدخل الرقم مجددًا.')
add('login_expired', '⌛️ مرحله ورود منقضی شد. /start رو بزن.', '⌛️ Login step expired. Send /start.', '⌛️ Время входа истекло. Отправьте /start.', '⌛️ 登录步骤已过期，请发送 /start。', '⌛️ انتهت صلاحية خطوة الدخول. أرسل /start.')
add('wait_seconds', '⏳ محدودیت تلگرام: {s} ثانیه صبر کن.', '⏳ Telegram rate limit: wait {s} seconds.', '⏳ Ограничение Telegram: подождите {s} сек.', '⏳ Telegram 频率限制：请等待 {s} 秒。', '⏳ تقييد من Telegram: انتظر {s} ثانية.')
add('login_failed', '❌ ورود ناموفق بود. /start رو بزن و دوباره تلاش کن.', '❌ Login failed. Send /start to try again.', '❌ Войти не удалось. Отправьте /start и повторите.', '❌ 登录失败，请发送 /start 重试。', '❌ فشل تسجيل الدخول. أرسل /start للمحاولة مجددًا.')
add('password_login_failed', '❌ ورود با رمز ناموفق بود. دوباره بفرست یا /cancel بزن.', '❌ Password login failed. Try again or send /cancel.', '❌ Вход с паролем не удался. Повторите или /cancel.', '❌ 密码登录失败，请重试或发送 /cancel。', '❌ فشل الدخول بكلمة المرور. حاول مجددًا أو أرسل /cancel.')
add('pending_cleanup_notice',
    '⏳ تا وقتی خروج همه دستگاه‌های دیگر تأیید نشده، خرید در انتظار می‌ماند و مبلغی به حساب شما اضافه نمی‌شود.\nاگر فراموش کنید سشن‌های فعال باقی‌مانده را از اکانت خارج کنید، ربات پس از گذشت حداقل ۲۴ ساعت از ورودش تلاش می‌کند آن‌ها را خارج کند. اعتبار پس از تأیید خروج همه سشن‌های دیگر به حساب شما اضافه می‌شود.',
    '⏳ The purchase stays pending, and no money is added to your balance until all other sessions are confirmed logged out. If you forget to terminate the remaining active sessions, the bot will try to terminate them at least 24 hours after it logged in. Your balance is credited after it confirms the other sessions are gone.',
    '⏳ Покупка остаётся в ожидании, и средства не зачисляются на ваш баланс, пока не будет подтверждён выход из остальных сеансов. Если вы забудете завершить оставшиеся активные сеансы, бот попытается сделать это не ранее чем через 24 часа после входа. Средства будут зачислены после подтверждения, что других сеансов не осталось.',
    '⏳ 在确认其他会话均已退出前，购买将保持待处理，款项不会计入您的余额。如果您忘记终止其余活跃会话，机器人将在登录至少 24 小时后尝试终止它们。确认其他会话已退出后，款项才会入账。',
    '⏳ تبقى عملية الشراء قيد الانتظار ولن يُضاف أي مبلغ إلى رصيدك حتى يتم التأكد من تسجيل الخروج من جميع الجلسات الأخرى. إذا نسيت إنهاء الجلسات النشطة المتبقية، فسيحاول البوت إنهاءها بعد مرور 24 ساعة على الأقل من تسجيل دخوله. يُضاف الرصيد بعد التأكد من خروج الجلسات الأخرى.')
add('spambot_limited',
    '❌ متاسفانه اکانتی که تحویل دادید توسط اسپم بات به عنوان ریپورت شده اعلام شده. اکانت های ریپورت را نمی‌پذیریم. ربات از اکانت شما خارج شد.',
    '❌ Unfortunately, SpamBot reported the account you submitted. We do not accept reported accounts. The bot has logged out of your account.',
    '❌ К сожалению, SpamBot сообщил, что предоставленный вами аккаунт имеет жалобы. Мы не принимаем такие аккаунты. Бот вышел из вашего аккаунта.',
    '❌ 抱歉，SpamBot 将您提交的账号标记为被举报。我们不接受被举报的账号。机器人已退出您的账号。',
    '❌ للأسف، أفاد سبام بوت بأن الحساب الذي قدمته مُبلّغ عنه. لا نقبل الحسابات المُبلّغ عنها. سجّل البوت الخروج من حسابك.')
add('spambot_check_failed',
    '❌ متاسفانه اکانتی که تحویل دادید توسط اسپم بات به عنوان ریپورت شده اعلام شده. اکانت های ریپورت را نمی‌پذیریم. ربات از اکانت شما خارج شد.',
    '❌ Unfortunately, SpamBot reported the account you submitted. We do not accept reported accounts. The bot has logged out of your account.',
    '❌ К сожалению, SpamBot сообщил, что предоставленный вами аккаунт имеет жалобы. Мы не принимаем такие аккаунты. Бот вышел из вашего аккаунта.',
    '❌ 抱歉，SpamBot 将您提交的账号标记为被举报。我们不接受被举报的账号。机器人已退出您的账号。',
    '❌ للأسف، أفاد سبام بوت بأن الحساب الذي قدمته مُبلّغ عنه. لا نقبل الحسابات المُبلّغ عنها. سجّل البوت الخروج من حسابك.')
add('channel_check_failed',
    '❌ متاسفانه این اکانت توسط تلگرام محدود شده و امکان ساخت کانال ندارد. مجموعه ما این اکانت هارا نمی‌پذیرد. ربات از اکانت شما خارج شد.',
    '❌ Unfortunately, this account has been restricted by Telegram and cannot create channels. We do not accept these accounts. The bot has logged out of your account.',
    '❌ К сожалению, Telegram ограничил этот аккаунт, и он не может создавать каналы. Мы не принимаем такие аккаунты. Бот вышел из вашего аккаунта.',
    '❌ 抱歉，此账号已被 Telegram 限制，无法创建频道。我们不接受此类账号。机器人已退出您的账号。',
    '❌ للأسف، قيّد تيليجرام هذا الحساب ولا يمكنه إنشاء قنوات. لا نقبل هذه الحسابات. سجّل البوت الخروج من حسابك.')
add('channel_cleanup_failed',
    '❌ کانال آزمایشی ساخته شد، اما حذف آن تأیید نشد؛ اکانت پذیرفته نشد. کانال <code>{title}</code> را از تلگرام حذف کن.',
    '❌ The test channel was created, but cleanup was not confirmed; the account was not accepted. Please delete <code>{title}</code> in Telegram.',
    '❌ Тестовый канал создан, но его удаление не подтверждено; аккаунт не принят. Удалите <code>{title}</code> в Telegram.',
    '❌ 测试频道已创建，但未确认已删除；账号未被接受。请在 Telegram 中删除 <code>{title}</code>。',
    '❌ أُنشئت القناة التجريبية لكن لم يتأكد حذفها؛ لم يُقبل الحساب. احذف <code>{title}</code> في Telegram.')
add('account_frozen',
    '❌ اکانت‌های فریز شده را نمی‌پذیریم. خرید این اکانت لغو شد.',
    '❌ We do not accept frozen accounts. This account sale has been cancelled.',
    '❌ Мы не принимаем замороженные аккаунты. Продажа этого аккаунта отменена.',
    '❌ 我们不接受已冻结的账号。此账号的出售已取消。',
    '❌ لا نقبل الحسابات المجمّدة. تم إلغاء بيع هذا الحساب.')
add('freeze_check_failed',
    '❌ بررسی وضعیت فریز اکانت ممکن نشد. اکانت پذیرفته نشد؛ بعداً دوباره تلاش کن.',
    '❌ Could not check whether this account is frozen. The account was not accepted; please try again later.',
    '❌ Не удалось проверить, заморожен ли аккаунт. Аккаунт не принят; повторите позже.',
    '❌ 无法检查此账号是否已冻结。账号未被接受，请稍后重试。',
    '❌ تعذّر التحقق مما إذا كان الحساب مجمّدًا. لم يُقبل الحساب؛ حاول لاحقًا.')
add('rejected_logout_failed',
    '⚠️ تلگرام خروج سشن جدید ربات را تأیید نکرد. از تنظیمات تلگرام ← دستگاه‌ها، سشن جدید ربات را خارج کن.',
    '⚠️ Telegram did not confirm logout of the bot’s new session. Terminate that session in Telegram Settings → Devices.',
    '⚠️ Telegram не подтвердил выход из нового сеанса бота. Завершите его в Telegram: Настройки → Устройства.',
    '⚠️ Telegram 未确认机器人的新会话已退出。请在 Telegram 设置 → 设备中终止该会话。',
    '⚠️ لم يؤكد Telegram تسجيل خروج جلسة البوت الجديدة. أنهِ هذه الجلسة من إعدادات Telegram ← الأجهزة.')
add('account_blocked', '❌ این اکانت مسدود/حذف شده است.', '❌ This account is blocked or deleted.', '❌ Аккаунт заблокирован или удалён.', '❌ 此账号已被封禁或删除。', '❌ هذا الحساب محظور أو محذوف.')
add('no_session', '❌ سشن ساخته نشد. /start رو بزن و دوباره تلاش کن.', '❌ Session was not created. Send /start to try again.', '❌ Сессия не создана. Отправьте /start и повторите.', '❌ 未创建会话，请发送 /start 重试。', '❌ لم تُنشأ الجلسة. أرسل /start وحاول مجددًا.')
add('finish_login_failed', '❌ خطا در تکمیل ورود. /start رو بزن.', '❌ Could not complete login. Send /start.', '❌ Не удалось завершить вход. Отправьте /start.', '❌ 无法完成登录，请发送 /start。', '❌ تعذر إكمال الدخول. أرسل /start.')
add('device_check_failed', '❌ بررسی دستگاه‌ها ناموفق بود. دوباره تلاش کن.', '❌ Device check failed. Try again.', '❌ Не удалось проверить устройства. Повторите.', '❌ 设备检查失败，请重试。', '❌ فشل التحقق من الأجهزة. حاول مجددًا.')
add('login_head', '🆗 اکانت <code>{phone}</code> وارد شد و سشن ذخیره شد.\n👤 یوزر: {user}\n', '🆗 Logged into <code>{phone}</code> and saved the session.\n👤 Username: {user}\n', '🆗 Вход в <code>{phone}</code> выполнен, сессия сохранена.\n👤 Имя: {user}\n', '🆗 已登录 <code>{phone}</code> 并保存会话。\n👤 用户名：{user}\n', '🆗 تم الدخول إلى <code>{phone}</code> وحفظ الجلسة.\n👤 اسم المستخدم: {user}\n')
add('no_devices', '🆗 هیچ دستگاه/سشن دیگری روی این اکانت فعال نیست.', '🆗 No other active devices or sessions.', '🆗 Других активных устройств и сессий нет.', '🆗 没有其他活跃设备或会话。', '🆗 لا توجد أجهزة أو جلسات أخرى نشطة.')
add('devices_title', '👀 <b>دستگاه‌های فعال روی اکانت:</b>', '👀 <b>Active devices on the account:</b>', '👀 <b>Активные устройства аккаунта:</b>', '👀 <b>账号的活跃设备：</b>', '👀 <b>الأجهزة النشطة في الحساب:</b>')
add('unknown_device', 'دستگاه ناشناس', 'Unknown device', 'Неизвестное устройство', '未知设备', 'جهاز غير معروف')
add('logout_instructions',
    '\n\n⛔️ <b>برای تأیید فروش، همه‌ی موارد بالا رو از اکانت خارج کن</b>\n📲 از داخل خود تلگرام: Settings → Devices → Terminate\n👍 بعد از اینکه از اکانت خارج شدی، دکمه «لاگ اوت کردم» رو بزن.',
    '\n\n⛔️ <b>Log out of all devices listed above to confirm the sale.</b>\n📲 In Telegram: Settings → Devices → Terminate\n👍 After you log out of the account, tap “I logged out”.',
    '\n\n⛔️ <b>Выйдите со всех перечисленных устройств, чтобы подтвердить продажу.</b>\n📲 В Telegram: Настройки → Устройства → Завершить сеанс\n👍 После выхода из аккаунта нажмите «Я вышел».',
    '\n\n⛔️ <b>请退出以上所有设备，以确认出售。</b>\n📲 在 Telegram 中：设置 → 设备 → 终止会话\n👍 退出账号后，点击“我已退出”。',
    '\n\n⛔️ <b>سجّل الخروج من جميع الأجهزة المذكورة لتأكيد البيع.</b>\n📲 في Telegram: الإعدادات ← الأجهزة ← إنهاء الجلسات\n👍 بعد تسجيل الخروج من الحساب، اضغط «سجّلت الخروج».')
add('auto_expired', '⌛️ بررسی خودکار ۵ دقیقه‌ای تمام شد.\nبعد از خروج از سشن‌های دیگر، برای بررسی روی «لاگ اوت کردم» بزن.', '⌛️ The 5-minute automatic checks have ended.\nAfter logging out other sessions, tap “I logged out” to check.', '⌛️ Пятиминутная автопроверка закончилась.\nПосле выхода из других сессий нажмите «Я вышел».', '⌛️ 5 分钟自动检查已结束。\n退出其他会话后，点击“我已退出”检查。', '⌛️ انتهت مدة التحقق التلقائي (5 دقائق).\nبعد الخروج من الجلسات الأخرى، اضغط «سجّلت الخروج» للتحقق.')
add('step_inactive', 'این مرحله فعال نیست. /start', 'This step is not active. /start', 'Этот шаг неактивен. /start', '此步骤未激活。/start', 'هذه الخطوة غير نشطة. /start')
add('wait_limit', '⏳ محدودیت تلگرام؛ کمی صبر کن.', '⏳ Telegram rate limit; please wait.', '⏳ Ограничение Telegram; подождите.', '⏳ Telegram 频率限制，请稍等。', '⏳ تقييد من Telegram؛ يرجى الانتظار.')
add('session_revoked', '❌ ربات از اکانت بیرون انداخته شده و سشن باطل شده. دوباره /start بزن', '❌ Session revoked. Send /start.', '❌ Сессия отозвана. Отправьте /start.', '❌ 会话已撤销，请发送 /start。', '❌ أُلغيت الجلسة. أرسل /start.')
add('retry_check', 'خطا در بررسی. دوباره بزن.', 'Check failed. Try again.', 'Ошибка проверки. Повторите.', '检查失败，请重试。', 'فشل التحقق. حاول مجددًا.')
add('sessions_remaining', '⛔️ {n} سشن باقی مونده', '⛔️ {n} sessions remain', '⛔️ Осталось сессий: {n}', '⛔️ 还剩 {n} 个会话', '⛔️ تبقّت {n} جلسات')
add('remaining_report', '⛔️ هنوز {n} سشن/دستگاه روی اکانت فعاله:\n\n{r}\n\n❌ همه رو خارج کن؛ بررسی خودکار تا پایان ۵ دقیقه ادامه داره.\nبرای بررسی فوری «لاگ اوت کردم» رو بزن.', '⛔️ {n} other sessions/devices are still active:\n\n{r}\n\n❌ Log them all out. Automatic checks run for up to 5 minutes.\nTap “I logged out” to check immediately.', '⛔️ Активных устройств/сессий: {n}\n\n{r}\n\n❌ Выйдите из всех. Автопроверка длится до 5 минут.\n«Я вышел» — проверить сразу.', '⛔️ 仍有 {n} 个其他活跃会话或设备：\n\n{r}\n\n❌ 请全部退出。自动检查最长持续 5 分钟。\n点击“我已退出”立即检查。', '⛔️ لا تزال {n} جلسات/أجهزة أخرى نشطة:\n\n{r}\n\n❌ سجّل الخروج منها جميعًا. يستمر التحقق التلقائي حتى 5 دقائق.\nاضغط «سجّلت الخروج» للتحقق فورًا.')
add('admin_only', '⛔️ فقط ادمین می‌تونه از این دستور استفاده کنه.', '⛔️ This command is for admins only.', '⛔️ Команда доступна только администратору.', '⛔️ 此命令仅限管理员使用。', '⛔️ هذا الأمر للمشرفين فقط.')
add('admin_panel_only', '⛔️ فقط ادمین می‌تونه از این پنل استفاده کنه.', '⛔️ This panel is for admins only.', '⛔️ Панель доступна только администратору.', '⛔️ 此面板仅限管理员使用。', '⛔️ هذه اللوحة للمشرفين فقط.')
add('choose_language_first', 'اول زبانت رو انتخاب کن.', 'Choose your language first.', 'Сначала выберите язык.', '请先选择语言。', 'اختر لغتك أولًا.')
add('invalid_language', 'زبان نامعتبره.', 'Invalid language.', 'Недопустимый язык.', '语言无效。', 'لغة غير صالحة.')
add('language_busy', 'برای تغییر زبان، اول مراحل فعلی رو تموم کن یا /cancel بزن.', 'Finish the current flow or send /cancel before changing language.', 'Завершите текущий процесс или отправьте /cancel перед сменой языка.', '更改语言前，请完成当前流程或发送 /cancel。', 'أكمل العملية الحالية أو أرسل /cancel قبل تغيير اللغة.')
