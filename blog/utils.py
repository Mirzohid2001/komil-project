"""Blog helper utilities (kept out of views to avoid circular imports)."""

def check_question_options_consistency(question_text, options):
    """
    Проверяет логическую связь между вопросом и вариантами ответов.
    
    Аргументы:
        question_text: текст вопроса
        options: список объектов Option
        
    Возвращает:
        bool: True если вопрос и варианты логически связаны, иначе False
    """
    question_text = question_text.lower()
    
    # 1. Проверка на вопросы о количестве/числе
    quantity_keywords = [
        'nechta', 'qancha', 'necha', 'nechanchi', 'qanchasi', 'miqdori', 'soni',
        'nechtasi', 'qaysisi', 'nechta', 'qaysi raqam', 'necha marta', 'necha kun',
        'qiymati qancha', 'qanday qiymat'
    ]
    
    is_quantity_question = any(keyword in question_text for keyword in quantity_keywords)
    
    if is_quantity_question:
        # Для вопросов о количестве варианты должны содержать числа
        has_numeric_options = False
        for option in options:
            # Проверяем, содержит ли вариант ответа числа или числовые значения
            if any(char.isdigit() for char in option.text):
                has_numeric_options = True
                break
        
        if not has_numeric_options:
            return False
    
    # 2. Проверка на вопросы "что нужно делать?"
    action_keywords = [
        'nima qilish kerak', 'qanday qilish kerak', 'kerak bo\'ladi', 'qilinadi',
        'bajariladi', 'amalga oshiriladi', 'qilish usuli', 'qanday amalga', 'qilish tartibi'
    ]
    
    is_action_question = any(keyword in question_text for keyword in action_keywords)
    
    if is_action_question:
        # Варианты ответов должны содержать глаголы действия
        action_verb_endings = [
            'lash', 'ish', 'ash', 'moq', 'sini', 'shni', 'tiladi', 'dirish', 'iladi'
        ]
        
        has_action_options = False
        for option in options:
            if any(option.text.lower().endswith(ending) for ending in action_verb_endings):
                has_action_options = True
                break
        
        if not has_action_options:
            return False
    
    # 3. Проверка на вопросы о времени
    time_keywords = [
        'qachon', 'qaysi vaqtda', 'qaysi muddatda', 'qancha vaqt', 'vaqti', 'soatda',
        'daqiqada', 'qaysi kun', 'qaysi oy', 'qaysi yil'
    ]
    
    is_time_question = any(keyword in question_text for keyword in time_keywords)
    
    if is_time_question:
        # Варианты ответов должны содержать указания на время/даты
        time_indicators = [
            'soat', 'daqiqa', 'kun', 'oy', 'yil', 'hafta', 'sana', 'muddat', 
            'boshla', 'tugash', 'yakunla', 'davomida', 'oralig\'ida'
        ]
        
        has_time_options = False
        for option in options:
            option_text = option.text.lower()
            if any(indicator in option_text for indicator in time_indicators) or any(char.isdigit() for char in option_text):
                has_time_options = True
                break
        
        if not has_time_options:
            return False
    
    # 4. Проверка на вопросы о месте или локации
    location_keywords = [
        'qayerda', 'qaysi joyda', 'qayerga', 'qaysi manzilda', 'joylashgan',
        'manzili', 'turadi', 'topiladi'
    ]
    
    is_location_question = any(keyword in question_text for keyword in location_keywords)
    
    if is_location_question:
        # Варианты ответов должны содержать указания на места
        location_indicators = [
            'xona', 'bino', 'markaz', 'joy', 'ko\'cha', 'viloyat', 'tuman', 'shahar', 
            'qishloq', 'mahalla', 'hudud', 'mintaqa', 'mamlakat', 'davlat'
        ]
        
        has_location_options = False
        for option in options:
            if any(indicator in option.text.lower() for indicator in location_indicators):
                has_location_options = True
                break
                
        if not has_location_options:
            return False
    
    # По умолчанию, если никаких проблем не найдено или тип вопроса не определен,
    # считаем что вопрос и варианты ответов соответствуют друг другу
    return True
