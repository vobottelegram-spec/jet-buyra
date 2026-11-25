# BIYORA + Jet Number روی یک ریپو / یک سرویس Railway

همه فایل‌ها بدون پوشه‌اند. هر دو ربات داخل یک کانتینر با `run.py` اجرا می‌شوند و از طریق رابط امضاشده روی 127.0.0.1 (فقط داخل کانتینر) به هم وصل‌اند. **رمز رابط و کلید رمزنگاری را لازم نیست دستی بسازی.**

## مراحل
1. همه فایل‌های این زیپ را (با فایل‌های نقطه‌دار `.env.example` و `.gitignore`) در ریشه یک ریپوی خصوصی GitHub بگذار. فایل `.env` واقعی را هرگز commit نکن.
2. Railway ← New Project ← Deploy from GitHub ← همین ریپو (Dockerfile خودکار شناسایی می‌شود؛ فقط **یک** سرویس).
3. سرویس ← Settings ← Volumes ← Add Volume ← Mount path: `/data`
4. سرویس ← Variables ← Raw Editor ← محتوای `.env.example` را بچسبان و پر کن:
   - `BIYORA_BOT_TOKEN` و `JETNUMBER_BOT_TOKEN` (دو توکن جدا از BotFather)
   - `API_ID` `API_HASH` `ADMIN_IDS` برای BIYORA
   - `OWNER_IDS` و بقیه برای Jet Number (اگر API تی‌نامبر نمی‌خواهی، `TNUMBER_API_KEY` را خالی بگذار)
5. Deploy. در Logs باید خطوط `[BIYORA]` و `[JetNumber]` را ببینی و `coloured buttons: ON`.
6. در Jet Number: تنظیمات عمومی ← «پنل دوم» روشن ← `/p2sync` ← `/p2price US 150000`.
7. اکانت تست خودت: در Railway Shell این را بزن `python import_test_account.py` (شماره + StringSession اکانت تستی؛ راهنمای ساخت StringSession بالای همان فایل است).

## نکات
- بدون Volume روی `/data` دیتابیس‌ها با هر deploy پاک می‌شوند (در لاگ هشدار می‌دهد).
- کلید رمزنگاری خودکار داخل `/data/data_keys.key` ساخته می‌شود؛ فقط برای تست. برای محصول واقعی `DATA_KEYS` را در Variables بگذار و یک نسخه آفلاین نگه دار.
- فروشنده واقعی به‌خاطر محدودیت تلگرام ۲۴ ساعت تا ورود به موجودی صبر می‌کند؛ برای تست از مرحله ۷ استفاده کن.
- Trial ریلوی: ۳۰ روز / ۵ دلار اعتبار یک‌باره؛ فقط اکانت و ربات تستی.
