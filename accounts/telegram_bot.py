"""Telegram Bot API — registratsiya so‘rovlari (webhook handler)."""
from __future__ import annotations

import logging
import re
import secrets
from typing import Any

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts.audit import log_compliance_event
from accounts.models import RegistrationRequest, TelegramBotSettings, TelegramDialog, User

logger = logging.getLogger(__name__)
UserModel = get_user_model()

API_BASE = 'https://api.telegram.org/bot{token}/{method}'

# Admin rolini Telegram orqali tanlash mumkin emas
SIGNUP_ROLES = [(v, lbl) for v, lbl in User.ROLE_CHOICES if v != 'admin']
SIGNUP_ROLE_BY_INDEX = {str(i): value for i, (value, _lbl) in enumerate(SIGNUP_ROLES)}


def get_bot_settings() -> TelegramBotSettings:
    """Admin paneldagi singleton sozlamalar."""
    try:
        return TelegramBotSettings.load()
    except Exception:
        # migrate oldin / DB yo‘q
        return TelegramBotSettings(pk=1)


def bot_configured() -> bool:
    cfg = get_bot_settings()
    return bool(cfg.is_enabled and (cfg.bot_token or '').strip())


def bot_username() -> str:
    return (get_bot_settings().bot_username or '').lstrip('@')


def webhook_secret() -> str:
    return (get_bot_settings().webhook_secret or '').strip()


def bot_deep_link() -> str:
    name = bot_username()
    return f'https://t.me/{name}?start=register' if name else ''


def admin_chat_ids() -> list[int]:
    raw = get_bot_settings().admin_chat_ids or ''
    ids: list[int] = []
    for part in str(raw).split(','):
        part = part.strip()
        if part.isdigit() or (part.startswith('-') and part[1:].isdigit()):
            ids.append(int(part))
    return ids


def _api(method: str, payload: dict | None = None, *, timeout: int = 20) -> dict:
    token = (get_bot_settings().bot_token or '').strip()
    if not token:
        return {'ok': False, 'description': 'Bot token Admin → Telegram sozlamalarida yo‘q'}
    url = API_BASE.format(token=token, method=method)
    try:
        resp = requests.post(url, json=payload or {}, timeout=timeout)
        data = resp.json()
        if not data.get('ok'):
            logger.warning('Telegram API %s: %s', method, data)
        return data
    except Exception:
        logger.exception('Telegram API %s failed', method)
        return {'ok': False, 'description': 'request failed'}


def set_webhook(url: str = '') -> dict:
    """Webhook URL o‘rnatish (Admin yoki management command)."""
    if not bot_configured():
        return {'ok': False, 'description': 'Bot yoqilmagan yoki token yo‘q'}
    if not url:
        root = getattr(settings, 'BASE_URL', '').rstrip('/')
        if not root:
            return {'ok': False, 'description': 'BASE_URL sozlanmagan (DJANGO_BASE_URL)'}
        url = f'{root}/accounts/telegram/webhook/'
    cfg = get_bot_settings()
    secret = cfg.ensure_webhook_secret()
    payload: dict[str, Any] = {
        'url': url,
        'allowed_updates': ['message', 'callback_query'],
        'drop_pending_updates': False,
        'secret_token': secret,
    }
    return _api('setWebhook', payload)


def delete_webhook() -> dict:
    return _api('deleteWebhook', {'drop_pending_updates': False})


def fetch_bot_username() -> str:
    """getMe orqali username olib DB ga yozadi."""
    data = _api('getMe')
    if not data.get('ok'):
        return ''
    username = (data.get('result') or {}).get('username') or ''
    if username:
        cfg = get_bot_settings()
        if cfg.bot_username != username:
            cfg.bot_username = username
            cfg.save(update_fields=['bot_username', 'updated_at'])
    return username


def send_message(
    chat_id: int,
    text: str,
    *,
    reply_markup: dict | None = None,
    parse_mode: str | None = None,
) -> dict:
    payload: dict[str, Any] = {
        'chat_id': chat_id,
        'text': text,
        'disable_web_page_preview': True,
    }
    if reply_markup is not None:
        payload['reply_markup'] = reply_markup
    if parse_mode:
        payload['parse_mode'] = parse_mode
    return _api('sendMessage', payload)


def answer_callback(callback_id: str, text: str = '') -> dict:
    return _api('answerCallbackQuery', {
        'callback_query_id': callback_id,
        'text': text[:180],
        'show_alert': bool(text),
    })


def role_keyboard() -> dict:
    """callback_data indeks orqali — Cyrillic/max 64 bayt cheklovi uchun."""
    rows = []
    row = []
    for i, (_value, label) in enumerate(SIGNUP_ROLES):
        row.append({'text': str(label)[:64], 'callback_data': f'role:{i}'})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{'text': '❌ Bekor', 'callback_data': 'cancel'}])
    return {'inline_keyboard': rows}


def admin_review_keyboard(request_id: int) -> dict:
    return {
        'inline_keyboard': [[
            {'text': '✅ Tasdiqlash', 'callback_data': f'approve:{request_id}'},
            {'text': '❌ Rad etish', 'callback_data': f'reject:{request_id}'},
        ]]
    }


def _dialog(chat_id: int, username: str = '') -> TelegramDialog:
    obj, _ = TelegramDialog.objects.get_or_create(
        chat_id=chat_id,
        defaults={'telegram_username': username or ''},
    )
    if username and obj.telegram_username != username:
        obj.telegram_username = username
        obj.save(update_fields=['telegram_username', 'updated_at'])
    return obj


def _reset_dialog(dialog: TelegramDialog) -> None:
    dialog.step = 'idle'
    dialog.draft = {}
    dialog.save(update_fields=['step', 'draft', 'updated_at'])


def _split_full_name(full_name: str) -> tuple[str, str]:
    """Mahalliy tartib: Familiya Ism → (first_name, last_name)."""
    parts = full_name.strip().split()
    if not parts:
        return '', ''
    if len(parts) == 1:
        return parts[0], ''
    # "Karimov Ali" / "Каримов Али" → first=Ali, last=Karimov
    return ' '.join(parts[1:]), parts[0]


def _slug_username(base: str) -> str:
    base = re.sub(r'[^a-zA-Z0-9_]+', '', base.lower().replace(' ', '_'))
    base = base[:20] or 'xodim'
    candidate = base
    n = 1
    while UserModel.objects.filter(username=candidate).exists():
        n += 1
        candidate = f'{base}{n}'[:30]
    return candidate


def generate_username(req: RegistrationRequest) -> str:
    if req.employee_id:
        raw = re.sub(r'[^a-zA-Z0-9_]+', '', req.employee_id.lower())
        if raw:
            return _slug_username(raw)
    first, last = _split_full_name(req.full_name)
    latin = re.sub(r'[^a-zA-Z0-9]+', '', f'{first}{last}')
    if latin:
        return _slug_username(latin)
    # Faqat kirill / boshqa harflar — Telegram ID asosida barqaror login
    return _slug_username(f'tg{req.telegram_id}')


def approve_registration(
    req: RegistrationRequest,
    *,
    actor=None,
    notify: bool = True,
) -> UserModel:
    """Pending so‘rovni tasdiqlab User yaratadi (atomic, race-safe)."""
    password = secrets.token_urlsafe(9)

    with transaction.atomic():
        locked = (
            RegistrationRequest.objects.select_for_update()
            .filter(pk=req.pk)
            .first()
        )
        if locked is None:
            raise ValueError('So‘rov topilmadi.')
        if locked.status != 'pending':
            raise ValueError('So‘rov allaqachon ko‘rib chiqilgan.')

        if UserModel.objects.filter(telegram_id=locked.telegram_id).exists():
            raise ValueError('Bu Telegram allaqachon hisobga bog‘langan.')

        first, last = _split_full_name(locked.full_name)
        username = generate_username(locked)

        try:
            user = UserModel.objects.create_user(
                username=username,
                password=password,
                first_name=first[:150],
                last_name=last[:150],
                role=locked.role if locked.role != 'admin' else 'офисный-персонал',
                employee_id=locked.employee_id or '',
                phone_number=locked.phone_number or '',
                telegram_id=locked.telegram_id,
                telegram_username=locked.telegram_username or '',
            )
        except IntegrityError as exc:
            raise ValueError('Foydalanuvchi yaratib bo‘lmadi (username/telegram band).') from exc

        locked.status = 'approved'
        locked.created_user = user
        locked.reviewed_by = actor if getattr(actor, 'pk', None) else None
        locked.reviewed_at = timezone.now()
        locked.save()
        req = locked

    log_compliance_event(
        event_type='registration_approved',
        actor=actor,
        subject_user=user,
        object_type='RegistrationRequest',
        object_id=req.pk,
        message=f'Telegram registratsiya tasdiqlandi: {username}',
        payload={'telegram_id': req.telegram_id, 'role': req.role},
    )

    if notify:
        login_url = getattr(settings, 'BASE_URL', '').rstrip('/') + '/accounts/login/'
        send_message(
            req.telegram_id,
            (
                f'✅ So‘rovingiz tasdiqlandi!\n\n'
                f'Login: {username}\n'
                f'Parol: {password}\n\n'
                f'Kirish: {login_url}\n'
                f'Parolni birinchi kirishdan keyin o‘zgartiring.'
            ),
        )
        for admin_id in admin_chat_ids():
            if admin_id != req.telegram_id:
                send_message(
                    admin_id,
                    f'✅ #{req.pk} tasdiqlandi → {username} ({req.full_name})',
                )
    return user


def reject_registration(
    req: RegistrationRequest,
    *,
    actor=None,
    note: str = '',
    notify: bool = True,
) -> None:
    with transaction.atomic():
        locked = (
            RegistrationRequest.objects.select_for_update()
            .filter(pk=req.pk)
            .first()
        )
        if locked is None:
            raise ValueError('So‘rov topilmadi.')
        if locked.status != 'pending':
            raise ValueError('So‘rov allaqachon ko‘rib chiqilgan.')

        locked.status = 'rejected'
        locked.reviewed_by = actor if getattr(actor, 'pk', None) else None
        locked.reviewed_at = timezone.now()
        locked.review_note = note or ''
        locked.save()
        req = locked

    log_compliance_event(
        event_type='registration_rejected',
        actor=actor,
        object_type='RegistrationRequest',
        object_id=req.pk,
        message=f'Telegram registratsiya rad: {req.full_name}',
        payload={'telegram_id': req.telegram_id, 'note': note},
    )

    if notify:
        send_message(
            req.telegram_id,
            '❌ So‘rovingiz rad etildi. Savol bo‘lsa administrator bilan bog‘laning.',
        )


def _start_registration(chat_id: int, username: str) -> None:
    if UserModel.objects.filter(telegram_id=chat_id).exists():
        user = UserModel.objects.get(telegram_id=chat_id)
        send_message(
            chat_id,
            f'Siz allaqachon ro‘yxatdan o‘tgansiz.\nLogin: {user.username}',
        )
        return

    pending = RegistrationRequest.objects.filter(
        telegram_id=chat_id, status='pending',
    ).first()
    if pending:
        send_message(
            chat_id,
            (
                f'So‘rovingiz ko‘rib chiqilmoqda (#{pending.pk}).\n'
                f'Admin tasdiqlagach login/parol shu yerga yuboriladi.'
            ),
        )
        return

    dialog = _dialog(chat_id, username)
    dialog.step = 'full_name'
    dialog.draft = {}
    dialog.save(update_fields=['step', 'draft', 'updated_at'])
    send_message(
        chat_id,
        (
            'Isomer Oil LMS — ro‘yxatdan o‘tish so‘rovi.\n\n'
            '1/4 · Familiya va ismingizni yozing (masalan: Karimov Ali):'
        ),
    )


def _notify_admins(req: RegistrationRequest) -> None:
    role_label = dict(User.ROLE_CHOICES).get(req.role, req.role)
    text = (
        f'🆕 Yangi registratsiya so‘rovi #{req.pk}\n\n'
        f'FIO: {req.full_name}\n'
        f'Tabel: {req.employee_id or "—"}\n'
        f'Rol: {role_label}\n'
        f'Tel: {req.phone_number or "—"}\n'
        f'Telegram: @{req.telegram_username or "—"}\n'
        f'ID: {req.telegram_id}'
    )
    markup = admin_review_keyboard(req.pk)
    targets = admin_chat_ids()
    if not targets:
        logger.warning('Admin Telegram ID bo‘sh — Admin → Telegram sozlamalar')
        return
    for chat_id in targets:
        send_message(chat_id, text, reply_markup=markup)


def _handle_text(chat_id: int, username: str, text: str) -> None:
    text = (text or '').strip()
    if text.startswith('/start'):
        _start_registration(chat_id, username)
        return
    if text in ('/cancel', 'bekor', 'Bekor'):
        dialog = _dialog(chat_id, username)
        _reset_dialog(dialog)
        send_message(chat_id, 'Bekor qilindi. Qayta boshlash: /start')
        return

    dialog = _dialog(chat_id, username)
    if dialog.step == 'full_name':
        if len(text) < 3:
            send_message(chat_id, 'FIO qisqa. Qayta yozing:')
            return
        dialog.draft = {**dialog.draft, 'full_name': text[:200]}
        dialog.step = 'employee_id'
        dialog.save(update_fields=['draft', 'step', 'updated_at'])
        send_message(
            chat_id,
            '2/4 · Tabel raqamingizni yozing (yo‘q bo‘lsa `-` yuboring):',
        )
        return

    if dialog.step == 'employee_id':
        emp = '' if text in ('-', '—', 'yoq', 'yo‘q', 'нет') else text[:40]
        dialog.draft = {**dialog.draft, 'employee_id': emp}
        dialog.step = 'role'
        dialog.save(update_fields=['draft', 'step', 'updated_at'])
        send_message(chat_id, '3/4 · Rolni tanlang:', reply_markup=role_keyboard())
        return

    if dialog.step == 'phone':
        phone = re.sub(r'[^\d+]', '', text)[:20]
        if len(re.sub(r'\D', '', phone)) < 7:
            send_message(chat_id, 'Telefon raqamini to‘g‘ri yozing (masalan: +998901112233):')
            return
        draft = dialog.draft or {}
        if not draft.get('full_name'):
            _reset_dialog(dialog)
            send_message(chat_id, 'Qayta boshlang: /start')
            return
        if RegistrationRequest.objects.filter(telegram_id=chat_id, status='pending').exists():
            _reset_dialog(dialog)
            send_message(chat_id, 'Allaqachon kutilayotgan so‘rov bor. Admin javobini kuting.')
            return

        role = draft.get('role') or 'офисный-персонал'
        if role == 'admin' or role not in dict(SIGNUP_ROLES):
            role = 'офисный-персонал'

        req = RegistrationRequest.objects.create(
            telegram_id=chat_id,
            telegram_username=username or '',
            full_name=draft.get('full_name', '')[:200],
            employee_id=draft.get('employee_id', '')[:40],
            role=role,
            phone_number=phone,
            status='pending',
        )
        _reset_dialog(dialog)
        log_compliance_event(
            event_type='registration_requested',
            object_type='RegistrationRequest',
            object_id=req.pk,
            message=f'Telegram so‘rov: {req.full_name}',
            payload={'telegram_id': chat_id, 'role': role},
        )
        send_message(
            chat_id,
            (
                f'So‘rov yuborildi (#{req.pk}).\n'
                f'Administrator tasdiqlagach login va parol shu chatga keladi.'
            ),
        )
        _notify_admins(req)
        return

    if dialog.step == 'role':
        send_message(chat_id, 'Iltimos, tugmalardan rolni tanlang:', reply_markup=role_keyboard())
        return

    send_message(chat_id, 'Ro‘yxatdan o‘tish uchun /start bosing.')


def _handle_callback(callback: dict) -> None:
    data = callback.get('data') or ''
    cb_id = callback.get('id') or ''
    msg = callback.get('message') or {}
    chat = msg.get('chat') or {}
    chat_id = chat.get('id')
    from_user = callback.get('from') or {}
    username = from_user.get('username') or ''

    if data == 'cancel':
        if chat_id:
            dialog = _dialog(int(chat_id), username)
            _reset_dialog(dialog)
            send_message(int(chat_id), 'Bekor qilindi. Qayta: /start')
        answer_callback(cb_id, 'Bekor')
        return

    if data.startswith('role:') and chat_id:
        role_key = data.split(':', 1)[1]
        role = SIGNUP_ROLE_BY_INDEX.get(role_key)
        if not role or role == 'admin':
            answer_callback(cb_id, 'Noto‘g‘ri rol')
            return
        dialog = _dialog(int(chat_id), username)
        if dialog.step != 'role':
            answer_callback(cb_id, 'Avval /start')
            return
        dialog.draft = {**dialog.draft, 'role': role}
        dialog.step = 'phone'
        dialog.save(update_fields=['draft', 'step', 'updated_at'])
        answer_callback(cb_id)
        send_message(int(chat_id), '4/4 · Telefon raqamingizni yozing (+998...):')
        return

    if data.startswith('approve:') or data.startswith('reject:'):
        action, _, raw_id = data.partition(':')
        try:
            req_id = int(raw_id)
        except ValueError:
            answer_callback(cb_id, 'Xato')
            return

        admin_ids = set(admin_chat_ids())
        # Bo‘sh ro‘yxat = Telegram orqali tasdiq yopiq (faqat Django Admin)
        if not admin_ids or int(from_user.get('id') or 0) not in admin_ids:
            answer_callback(cb_id, 'Faqat admin')
            return

        try:
            req = RegistrationRequest.objects.get(pk=req_id)
        except RegistrationRequest.DoesNotExist:
            answer_callback(cb_id, 'Topilmadi')
            return

        if req.status != 'pending':
            answer_callback(cb_id, f'Holat: {req.get_status_display()}')
            return

        try:
            if action == 'approve':
                user = approve_registration(req, actor=None, notify=True)
                answer_callback(cb_id, f'Tasdiqlandi: {user.username}')
            else:
                reject_registration(req, actor=None, notify=True)
                answer_callback(cb_id, 'Rad etildi')
        except ValueError as exc:
            answer_callback(cb_id, str(exc)[:180])
        return

    answer_callback(cb_id)


def process_update(update: dict) -> None:
    """Webhook / polling dan kelgan bitta update."""
    if not bot_configured():
        return
    if 'callback_query' in update:
        _handle_callback(update['callback_query'])
        return
    message = update.get('message') or update.get('edited_message')
    if not message:
        return
    chat = message.get('chat') or {}
    chat_id = chat.get('id')
    if chat_id is None:
        return
    from_user = message.get('from') or {}
    username = from_user.get('username') or ''
    text = message.get('text') or ''
    if text:
        _handle_text(int(chat_id), username, text)
