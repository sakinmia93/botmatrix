# libs.TelegramSession

## Login flow (easy)

```python
s = libs.TelegramSession.create(
    api_id=..., api_hash=..., phone="+8801...",
    device_model="TgAcc",          # shown in Telegram login alert
    system_version="Android 14",
    app_version="BotMatrix 2.0",
)
# optional later:
libs.TelegramSession.setDevice(s, device_model="iPhone 15", system_version="iOS 18")

r = libs.TelegramSession.sendCode(s)           # auto channel
# r = libs.TelegramSession.sendCode(s, via="sms")  # force SMS when allowed
# r.code_via -> app | sms | call | flash_call | ...
# r.code_message -> human text

r = libs.TelegramSession.verifyCode(s, code="12345")
# wrong code -> can_retry_code=True, session NOT killed
# 2FA needed -> password_required, then:
r = libs.TelegramSession.verifyPassword(s, password="...")
# wrong password -> can_retry_password=True, session kept

libs.TelegramSession.resendCode(s)             # same session
libs.TelegramSession.resendCode(s, via="sms")  # prefer SMS
```

## Business helpers
listSessions / listByCountry / checkAccount / tags / notes / trace / validateApi / Stars...

On import expands `tg_gz_*.b64`. Needs `telethon`.
