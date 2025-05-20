"""
Telegram-бот для определения вероятных этничностей/национальностей по имени.

Бот использует API nationalize.io для получения данных и строит
столбчатую диаграмму с результатами.
"""

import matplotlib

matplotlib.use('Agg')  # Устанавливаем бэкенд для работы без GUI
import telebot
import requests
import pycountry
import matplotlib.pyplot as plt
from io import BytesIO

# Конфигурационные константы
API_KEY = ''  # Ключ для доступа к API nationalize.io
bot = telebot.TeleBot("")  # Инициализация бота

# Кэш для хранения результатов
request_cache = {}

def get_country_name(country_code):
    """
    Преобразует код страны в её полное название.

    Args:
        country_code (str): Двухбуквенный код страны (например, 'RU', 'US')

    Returns:
        str: Название страны или строка с сообщением о неизвестной стране

    Examples:
        >>> get_country_name('RU')
        'Russian Federation'
        >>> get_country_name('XX')
        'Неизвестная страна (XX)'
    """
    try:
        return pycountry.countries.get(alpha_2=country_code).name
    except (AttributeError, LookupError):
        return f"Неизвестная страна ({country_code})"


def create_bar_chart(countries_data):
    """
    Создает столбчатую диаграмму распределения национальностей.

    Args:
        countries_data (list): Список словарей с данными о странах:
            [{'country_id': 'RU', 'probability': 0.5}, ...]

    Returns:
        BytesIO: Буфер с изображением графика в формате PNG
    """
    # Извлекаем названия стран и вероятности
    country_names = [get_country_name(c['country_id']) for c in countries_data]
    probabilities = [c['probability'] * 100 for c in countries_data]

    # Создаем фигуру и оси
    plt.figure(figsize=(10, 5))

    # Строим столбчатую диаграмму
    bars = plt.bar(country_names, probabilities, color='skyblue')

    # Настраиваем оформление графика
    plt.title('Вероятность этничностей/национальностей')
    plt.ylabel('Вероятность (%)')
    plt.xticks(rotation=45)  # Поворачиваем подписи для лучшей читаемости

    # Добавляем значения на каждый столбец
    for bar in bars:
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2.,
            height,
            f'{height:.1f}%',
            ha='center',
            va='bottom'
        )

    # Сохраняем график в буфер
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    plt.close()  # Закрываем фигуру для освобождения памяти
    buf.seek(0)  # Перемещаем указатель в начало буфера

    return buf


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """
    Обработчик команд /start и /help. Отправляет приветственное сообщение.
    """
    welcome_message = (
        "👋 Привет! Отправь мне имя/фамилию, и я определю 5 наиболее вероятных этничностей/национальностей.\n\n"
        "Примеры имен для теста:\n"
        "• Александр\n"
        "• Trump\n"
        "• Kim\n"
        "• Mohammed"
    )
    bot.reply_to(message, welcome_message)


@bot.message_handler(func=lambda message: True)
def handle_name(message):
    """
    Основной обработчик текстовых сообщений. Анализирует имя и возвращает результаты.
    """
    name = message.text.strip()

    # Валидация ввода
    if len(name) < 2:
        bot.reply_to(message, "❌ Имя(Фамилия) должно содержать минимум 2 символа")
        return

    try:
        # Отправляем запрос к API
        response = requests.get(
            "https://api.nationalize.io/",
            params={'name': name, 'api_key': API_KEY},
            timeout=15
        )
        response.raise_for_status()  # Проверяем на ошибки HTTP

        # Парсим ответ API
        data = response.json()
        countries = data.get('country', [])

        if not countries:
            bot.reply_to(message, "😞 Не удалось определить этничность/национальность. Возможно, имя/фамилия просто очень редкая!")
            return

        # Сортируем страны по вероятности и берем топ-5
        top_countries = sorted(
            countries,
            key=lambda x: x['probability'],
            reverse=True
        )[:5]

        # Форматируем результаты для вывода
        result = [
            f"{i}. {get_country_name(c['country_id'])} - {c['probability'] * 100:.1f}%"
            for i, c in enumerate(top_countries, 1)
        ]

        # Сохраняем данные в кэш
        cache_key = f"{message.chat.id}-{name}"
        request_cache[cache_key] = top_countries  # Сохраняем топ-5

        # Создаем кнопку с уникальным ключом кэша
        markup = telebot.types.InlineKeyboardMarkup()
        btn = telebot.types.InlineKeyboardButton(
            text="📊 Показать диаграммой",
            callback_data=f"graph_{cache_key}"  # Используем ключ кэша
        )
        markup.add(btn)

        # Отправляем результаты пользователю
        bot.send_message(
            chat_id=message.chat.id,
            text=f"🎯 Топ-5 этничностей/национальностей для {name}:\n" + "\n".join(result),
            reply_markup=markup
        )

    except requests.exceptions.RequestException as e:
        # Обработка ошибок сети и API
        bot.reply_to(message, f"⚠️ El problema - Ошибка при запросе к API: {str(e)}")
    except Exception as e:
        # Обработка прочих ошибок
        bot.reply_to(message, f"⚠️ El problema - Произошла непредвиденная ошибка: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data.startswith('graph_'))
def send_graph(call):
    """
       Обработчик нажатия кнопки "Показать график". Генерирует и отправляет диаграмму.
    """
    # Извлекаем ключ кэша из callback_data
    cache_key = call.data[6:]

    # Получаем данные из кэша
    top_countries = request_cache.get(cache_key)

    if not top_countries:
        bot.answer_callback_query(
            call.id,
            text="Данные устарели или отсутствуют",
            show_alert=True
        )
        return

    # Удаляем данные из кэша после использования (опционально)
    del request_cache[cache_key]

    # Создаем и отправляем график
    try:
        chart = create_bar_chart(top_countries)
        bot.send_photo(
            chat_id=call.message.chat.id,
            photo=chart,
            caption=f"📊 Распределение для {cache_key.split('-')[1]}"  # Извлекаем имя из ключа
        )
    except Exception as e:
        bot.answer_callback_query(
            call.id,
            text=f"Ошибка создания графика: {str(e)}",
            show_alert=True
        )

if __name__ == "__main__":
    print("Бот запущен и готов к работе...")
    bot.polling(none_stop=True)  # Запускаем бота с автоматическим переподключением