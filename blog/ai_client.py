"""
Bepul AI providerlari orqali test savollari yaratish.

Qo‘llab-quvvatlanadi:
- groq   — https://console.groq.com (karta shart emas, bepul limit)
- gemini — Google AI Studio (bepul limit)

Kalit yo‘q yoki xato bo‘lsa — chaqiruvchi shablon generatorga qaytadi.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
GEMINI_URL = (
    'https://generativelanguage.googleapis.com/v1beta/models/'
    '{model}:generateContent'
)

DEFAULT_MODELS = {
    'groq': 'llama-3.3-70b-versatile',
    'gemini': 'gemini-2.0-flash',
}


def ai_is_configured() -> bool:
    provider = getattr(settings, 'AI_PROVIDER', 'groq') or 'groq'
    if provider in ('off', 'none', 'template'):
        return False
    return bool(getattr(settings, 'AI_API_KEY', '') or '')


def ai_status() -> dict[str, Any]:
    provider = getattr(settings, 'AI_PROVIDER', 'groq') or 'groq'
    configured = ai_is_configured()
    return {
        'provider': provider,
        'configured': configured,
        'model': getattr(settings, 'AI_MODEL', '') or DEFAULT_MODELS.get(provider, ''),
        'label': {
            'groq': 'Groq (Llama) — bepul',
            'gemini': 'Google Gemini — bepul',
            'off': 'O‘chirilgan (faqat shablon)',
            'template': 'Faqat shablon',
        }.get(provider, provider),
    }


def _role_topic(role: str) -> str:
    topics = {
        'Оператор': 'zavod operatori, uskunalar, xavfsizlik texnikasi',
        'механик': 'mexanik, dastgoh sozlash, taʼmirlash',
        'электрик': 'elektr montyori, elektr xavfsizligi',
        'сварщик': 'payvandlash, himoya vositalari',
        'технолог': 'texnologik jarayon, sifat nazorati',
        'офисный-персонал': 'ofis xavfsizligi, mehnat muhofazasi',
        'Диспетчер': 'dispetcherlik, smena boshqaruvi',
        'охраник': 'qo‘riqlash, kirish nazorati',
        'admin': 'axborot xavfsizligi, tizim boshqaruvi',
        'склад': 'ombor, yuklash-tushirish xavfsizligi',
        'КИП и А': 'KIP va avtomatika',
        'слесарь': 'chilangar ishlari',
        'естокада': 'estakada / ishlab chiqarish liniyasi',
        'повар': 'oshxona gigiyenasi va xavfsizlik',
        'уборщик': 'tozalash xavfsizligi',
        'temiryo`lchi': 'temir yo‘l xavfsizligi',
    }
    return topics.get(role, f'zavod xodimi ({role})')


def _build_prompt(role: str, num_questions: int) -> str:
    topic = _role_topic(role)
    return f"""Sen zavod o‘quv tizimi uchun test tuzuvchi mutaxassissan.
Rol: {role} ({topic}).
Til: o‘zbek (lotin yozuvida).

{num_questions} ta test savoli yarat. Har birida:
- aniq, amaliy savol
- 4 ta javob varianti
- faqat BITTA to‘g‘ri javob

Faqat JSON massiv qaytar (boshqa matn yo‘q):
[
  {{
    "text": "Savol matni?",
    "options": [
      {{"text": "Variant A", "is_correct": true}},
      {{"text": "Variant B", "is_correct": false}},
      {{"text": "Variant C", "is_correct": false}},
      {{"text": "Variant D", "is_correct": false}}
    ]
  }}
]

Qoidalar:
- Agar savolda "qancha/nechta" bo‘lsa, variantlarda raqam bo‘lsin.
- Agar vaqt haqida bo‘lsa, variantlarda daqiqa/soat/kun bo‘lsin.
- Umumiy gaplar emas, zavod amaliyotiga yaqin savollar.
"""


def _extract_json_array(text: str) -> list:
    text = (text or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and 'questions' in data:
            return data['questions']
    except json.JSONDecodeError:
        pass
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        return json.loads(match.group(0))
    raise ValueError('AI javobidan JSON o‘qib bo‘lmadi')


def _normalize_questions(raw: list, num_questions: int) -> list[dict]:
    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = (item.get('text') or '').strip()
        options = item.get('options') or []
        if not text or not isinstance(options, list):
            continue
        norm_opts = []
        for opt in options:
            if not isinstance(opt, dict):
                continue
            ot = (opt.get('text') or '').strip()
            if not ot:
                continue
            norm_opts.append({
                'text': ot,
                'is_correct': bool(opt.get('is_correct')),
            })
        if len(norm_opts) < 2:
            continue
        # Faqat bitta to‘g‘ri
        correct_count = sum(1 for o in norm_opts if o['is_correct'])
        if correct_count == 0:
            norm_opts[0]['is_correct'] = True
        elif correct_count > 1:
            seen = False
            for o in norm_opts:
                if o['is_correct']:
                    if seen:
                        o['is_correct'] = False
                    seen = True
        # 4 tagacha to‘ldirish
        while len(norm_opts) < 4:
            norm_opts.append({
                'text': f'Noto‘g‘ri variant {len(norm_opts)}',
                'is_correct': False,
            })
        cleaned.append({'text': text, 'options': norm_opts[:4]})
        if len(cleaned) >= num_questions:
            break
    return cleaned


def _call_groq(prompt: str) -> str:
    api_key = settings.AI_API_KEY
    model = getattr(settings, 'AI_MODEL', '') or DEFAULT_MODELS['groq']
    resp = requests.post(
        GROQ_URL,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'model': model,
            'temperature': 0.7,
            'messages': [
                {
                    'role': 'system',
                    'content': 'Sen JSON formatida javob beradigan test generatorisan.',
                },
                {'role': 'user', 'content': prompt},
            ],
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['choices'][0]['message']['content']


def _call_gemini(prompt: str) -> str:
    api_key = settings.AI_API_KEY
    model = getattr(settings, 'AI_MODEL', '') or DEFAULT_MODELS['gemini']
    url = GEMINI_URL.format(model=model)
    resp = requests.post(
        url,
        params={'key': api_key},
        json={
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature': 0.7,
                'responseMimeType': 'application/json',
            },
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    return data['candidates'][0]['content']['parts'][0]['text']


def generate_questions_via_ai(role: str, num_questions: int = 30) -> list[dict]:
    """
    Bepul AI orqali savollar. Muvaffaqiyatsiz bo‘lsa exception.
    """
    if not ai_is_configured():
        raise RuntimeError('AI sozlanmagan (AI_API_KEY yo‘q)')

    provider = (getattr(settings, 'AI_PROVIDER', 'groq') or 'groq').lower()
    prompt = _build_prompt(role, num_questions)

    # Groq limitlari uchun katta so‘rovlarni bo‘laklash
    batch_size = 10 if provider == 'groq' else min(num_questions, 20)
    collected: list[dict] = []
    remaining = num_questions

    while remaining > 0:
        n = min(batch_size, remaining)
        batch_prompt = _build_prompt(role, n) if n != num_questions else prompt
        if provider == 'gemini':
            content = _call_gemini(batch_prompt)
        elif provider == 'groq':
            content = _call_groq(batch_prompt)
        else:
            raise ValueError(f"Noma'lum AI_PROVIDER: {provider}")

        batch = _normalize_questions(_extract_json_array(content), n)
        if not batch:
            raise ValueError('AI bo‘sh javob qaytardi')
        collected.extend(batch)
        remaining = num_questions - len(collected)
        if len(batch) < max(1, n // 2):
            # Progress sekin — to‘xtatamiz, mavjudini qaytaramiz
            break

    if not collected:
        raise ValueError('AI savol yaratolmadi')
    return collected[:num_questions]
