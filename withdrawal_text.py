
TEXT = {
    'withdraw_btn': ('برداشت موجودی', 'Withdraw balance', 'Вывести средства', '提现余额', 'سحب الرصيد'),
    'request_btn': ('درخواست برداشت موجودی', 'Request withdrawal', 'Запросить вывод', '申请提现', 'طلب سحب الرصيد'),
    'page': (
        '💳 <b>برداشت موجودی</b>\n\n💰 موجودی قابل برداشت: <b>{balance} دلار</b>\n≈ {balance_toman} تومان\n\n💸 مجموع برداشت‌های پرداخت‌شده: <b>{withdrawn} دلار</b>\n≈ {withdrawn_toman} تومان\n\n{rate_info}',
        '💳 <b>Withdraw balance</b>\n\n💰 Available: <b>${balance}</b>\n≈ {balance_toman} toman\n\n💸 Total paid withdrawals: <b>${withdrawn}</b>\n≈ {withdrawn_toman} toman\n\n{rate_info}',
        '💳 <b>Вывод средств</b>\n\n💰 Доступно: <b>{balance} USD</b>\n≈ {balance_toman} томанов\n\n💸 Всего выплачено: <b>{withdrawn} USD</b>\n≈ {withdrawn_toman} томанов\n\n{rate_info}',
        '💳 <b>提现余额</b>\n\n💰 可用余额：<b>{balance} 美元</b>\n≈ {balance_toman} 土曼\n\n💸 已支付提现总额：<b>{withdrawn} 美元</b>\n≈ {withdrawn_toman} 土曼\n\n{rate_info}',
        '💳 <b>سحب الرصيد</b>\n\n💰 الرصيد المتاح: <b>{balance} دولار</b>\n≈ {balance_toman} تومان\n\n💸 إجمالي السحوبات المدفوعة: <b>{withdrawn} دولار</b>\n≈ {withdrawn_toman} تومان\n\n{rate_info}'),
    'rate_info': (
        'نرخ دلار: هر دلار {rate} تومان',
        'USD rate: {rate} toman per USD',
        'Курс доллара: {rate} томанов за USD',
        '美元汇率：每美元 {rate} 土曼',
        'سعر الدولار: {rate} تومان لكل دولار'),
    'rate_unavailable': ('نرخ تازه ارز در دسترس نیست؛ معادل تومان نمایش داده نمی‌شود.', 'A fresh rate is unavailable; toman equivalents are not shown.', 'Свежий курс недоступен; эквивалент в томанах не показан.', '当前汇率不可用，无法显示土曼等值。', 'سعر صرف حديث غير متاح؛ لا يظهر المقابل بالتومان.'),
    'unavailable': ('نامشخص', 'Unavailable', 'Недоступно', '不可用', 'غير متاح'),
    'ask_amount': ('💵 مبلغ برداشت را به دلار بفرست.\nمثال: <code>0.183</code>\n\nموجودی قابل برداشت: <b>{balance} دلار</b>\nحداکثر ۶ رقم اعشار. /cancel برای لغو.', '💵 Send the withdrawal amount in USD.\nExample: <code>0.183</code>\n\nAvailable: <b>${balance}</b>\nUp to 6 decimal places. /cancel to cancel.', '💵 Отправьте сумму вывода в USD.\nНапример: <code>0.183</code>\n\nДоступно: <b>{balance} USD</b>\nДо 6 знаков после запятой. /cancel — отмена.', '💵 请发送美元提现金额。\n例如：<code>0.183</code>\n\n可用余额：<b>{balance} 美元</b>\n最多 6 位小数。发送 /cancel 取消。', '💵 أرسل مبلغ السحب بالدولار.\nمثال: <code>0.183</code>\n\nالمتاح: <b>{balance} دولار</b>\nحتى 6 منازل عشرية. أرسل /cancel للإلغاء.'),
    'invalid_amount': ('❌ مبلغ معتبر به دلار بفرست؛ بیشتر از موجودی نباشه و حداکثر ۶ رقم اعشار داشته باشه.', '❌ Send a valid USD amount no greater than your balance, with at most 6 decimal places.', '❌ Укажите сумму в USD не больше доступного баланса, до 6 знаков после запятой.', '❌ 请输入不超过可用余额的有效美元金额，最多 6 位小数。', '❌ أرسل مبلغًا صحيحًا بالدولار لا يتجاوز الرصيد وبحد أقصى 6 منازل عشرية.'),
    'no_balance': ('❌ موجودی قابل برداشتت صفره.', '❌ Your available balance is zero.', '❌ Доступный баланс равен нулю.', '❌ 可用余额为零。', '❌ رصيدك المتاح صفر.'),
    'ask_wallet': ('💎 آدرس کیف پول TON خودت رو بفرست.\nمبلغ درخواست: <b>{amount} دلار</b>\n\nآدرس رو با دقت بررسی کن؛ مسئولیت صحت و امکان دریافت با خودته. /cancel برای لغو.', '💎 Send your TON wallet address.\nRequested amount: <b>${amount}</b>\n\nCheck it carefully; you are responsible for its accuracy and ability to receive. /cancel to cancel.', '💎 Отправьте адрес TON-кошелька.\nСумма: <b>{amount} USD</b>\n\nВнимательно проверьте адрес; вы отвечаете за его правильность и возможность получения средств. /cancel — отмена.', '💎 请发送您的 TON 钱包地址。\n申请金额：<b>{amount} 美元</b>\n\n请仔细检查地址；您需自行负责地址的正确性及其接收资金的能力。发送 /cancel 取消。', '💎 أرسل عنوان محفظة TON الخاصة بك.\nالمبلغ المطلوب: <b>{amount} دولار</b>\n\nتحقق من العنوان بعناية؛ أنت مسؤول عن صحته وإمكانية استلام الأموال عليه. أرسل /cancel للإلغاء.'),
    'bad_wallet': ('❌ آدرس کیف پول TON معتبر نیست یا مخصوص شبکه آزمایشی است. دوباره بفرست.', '❌ Invalid or test-only TON address. Send it again.', '❌ Неверный или тестовый адрес TON. Отправьте его ещё раз.', '❌ TON 地址无效或仅用于测试网络，请重新发送。', '❌ عنوان TON غير صالح أو مخصص للاختبار. أرسله مجددًا.'),
    'balance_changed': ('❌ موجودی کافی نیست یا تغییر کرده. دوباره تلاش کن.', '❌ Insufficient balance or balance has changed. Try again.', '❌ Недостаточно средств или баланс изменился. Повторите.', '❌ 余额不足或已发生变化，请重试。', '❌ الرصيد غير كافٍ أو تغير. حاول مجددًا.'),
    'submitted': ('✅ درخواست برداشت <b>#{id}</b> به مبلغ <b>{amount} دلار</b> ثبت شد و در انتظار بررسی ادمینه.', '✅ Withdrawal request <b>#{id}</b> for <b>${amount}</b> was submitted and is awaiting admin review.', '✅ Запрос <b>#{id}</b> на <b>{amount} USD</b> создан и ожидает проверки администратором.', '✅ <b>#{id}</b> 号提现申请（<b>{amount} 美元</b>）已提交，等待管理员处理。', '✅ تم تقديم طلب السحب <b>#{id}</b> بقيمة <b>{amount} دولار</b> وهو بانتظار مراجعة المشرف.'),
    'paid': ('🎉 برداشت <b>#{id}</b> شما به مبلغ <b>{amount} دلار</b> با موفقیت انجام شد. 💰', '🎉 Your withdrawal <b>#{id}</b> for <b>${amount}</b> was completed successfully. 💰', '🎉 Ваш вывод <b>#{id}</b> на сумму <b>{amount} USD</b> успешно выполнен. 💰', '🎉 您的 <b>#{id}</b> 号提现（<b>{amount} 美元</b>）已成功完成。 💰', '🎉 تم سحب مبلغ <b>{amount} دولار</b> بنجاح في طلبك <b>#{id}</b>. 💰'),
    'flow_busy': ('اول عملیات فعلی رو تموم کن یا /cancel رو بزن.', 'Finish the current operation or send /cancel first.', 'Сначала завершите действие или отправьте /cancel.', '请先完成当前操作或发送 /cancel。', 'أكمل العملية الحالية أو أرسل /cancel أولًا.'),
}


def install(catalog):
    for key, variants in TEXT.items():
        catalog.add('withdraw_' + key, *variants)
