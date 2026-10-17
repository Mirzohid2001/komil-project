"""Savol turlari bo‘yicha javobni baholash."""

from __future__ import annotations


def normalize_text(value: str) -> str:
    return ' '.join((value or '').strip().lower().split())


def grade_question(question, raw_answer):
    """
    raw_answer:
      - single / true_false: option id (int/str)
      - multi: list of option ids
      - short: text str
      - None / missing: noto‘g‘ri
    Returns: (is_correct: bool, payload dict for UserAnswer)
    """
    qtype = question.question_type or question.Q_SINGLE
    payload = {
        'selected_option_id': None,
        'selected_option_ids': [],
        'text_answer': '',
    }
    own_ids = set(question.options.values_list('id', flat=True))

    if qtype == question.Q_SHORT:
        text = str(raw_answer or '').strip()
        payload['text_answer'] = text[:500]
        accepted = {normalize_text(a) for a in question.accepted_answer_list()}
        ok = bool(text) and normalize_text(text) in accepted
        return ok, payload

    if qtype == question.Q_MULTI:
        if isinstance(raw_answer, (list, tuple)):
            ids = []
            for x in raw_answer:
                try:
                    ids.append(int(x))
                except (TypeError, ValueError):
                    continue
        elif raw_answer in (None, ''):
            ids = []
        else:
            # Bitta id kelib qolsa ham listga aylantiramiz
            try:
                ids = [int(raw_answer)]
            except (TypeError, ValueError):
                ids = []
        # Faqat shu savolga tegishli variantlar
        ids = sorted({i for i in ids if i in own_ids})
        payload['selected_option_ids'] = ids
        if ids:
            payload['selected_option_id'] = ids[0]
        correct_ids = sorted(
            question.options.filter(is_correct=True).values_list('id', flat=True)
        )
        ok = bool(correct_ids) and ids == list(correct_ids)
        return ok, payload

    # single / true_false
    if raw_answer in (None, ''):
        return False, payload
    try:
        oid = int(raw_answer)
    except (TypeError, ValueError):
        return False, payload
    if oid not in own_ids:
        return False, payload
    payload['selected_option_id'] = oid
    payload['selected_option_ids'] = [oid]
    correct = question.get_correct_option()
    ok = bool(correct) and correct.id == oid
    return ok, payload
