import threading

from telebot import types

import config
import telebot
import uuid
import pickle
import time
from telebot.types import InputMediaPhoto

bot = telebot.TeleBot(config.token)
advert_dict = {}
unfound_media_group_id = []
lock = threading.Lock()


def save_advert():
    global advert_dict
    lock.acquire()
    pickle.dump(advert_dict, open('advertisements', 'wb'))
    lock.release()


def load_advert():
    global advert_dict
    advert_dict = pickle.load(open('advertisements', 'rb'))


class Advert:
    def __init__(self, contact, author_chat_id):
        self.contact = '@' + contact
        self.author_chat_id = author_chat_id
        self.photo = []
        self.sell = None
        self.description = None
        self.ready = False


@bot.message_handler(commands=['start', 'add'])
def select_advert_type(command):
    if command.from_user.username:
        keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        button_buy = types.KeyboardButton(text="Buy item")
        button_sell = types.KeyboardButton(text="Sell item")
        keyboard.add(button_buy, button_sell)
        msg = bot.send_message(command.chat.id, "Welcome"
                                                "Do you wish to buy or sell?", reply_markup=keyboard)
        bot.register_next_step_handler(msg, sell_or_buy)
    else:
        bot.send_message(command.chat.id, "It's required to have a username in Telegram. Please set it up in settings")


@bot.message_handler(commands=['clear'])
def clear_command(command):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    clear_button = types.InlineKeyboardButton(text='Clear', callback_data='clear')
    cancel_button = types.InlineKeyboardButton(text='Cancel', callback_data='cancel')
    keyboard.add(clear_button, cancel_button)
    save_advert()
    bot.send_message(command.chat.id, "Clear all unpublished advertisements from you?", reply_markup=keyboard)


@bot.message_handler(commands=['help'])
def show_help(command):
    bot.send_message(command.chat.id, "/help - show this help\n/add - add new "
                                      "advertisements\n/clear - clear all unpublished advertisements from you")


def clear(message):
    load_advert()
    lock.acquire()
    indexes = []
    for key, value in advert_dict.items():
        if (value.author_chat_id == message.from_user.id) and (value.ready is False):
            indexes.append(key)
    for index in indexes:
        del advert_dict[index]
    lock.release()


def sell_or_buy(message):
    if message.text == 'Buy item':
        start_buy_advertisements(message)
    elif message.text == "Sell item":
        start_sell_advertisement(message)
    else:
        bot.send_message(message.from_user.id, "Choose one of the options")
        select_advert_type(message)


def start_buy_advertisements(message):
    load_advert()
    advert = Advert(message.from_user.username, message.chat.id)
    advert.sell = False
    index = str(uuid.uuid1())
    advert_dict[index] = advert
    msg = bot.send_message(advert_dict[index].author_chat_id,
                           "Send a photo of the item you want to buy. If you have no photo - add a description."
                           "Your contact will be added automatically.",
                           reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, get_description, index)


def start_sell_advertisement(advertisement):
    load_advert()
    advert = Advert(advertisement.from_user.username, advertisement.chat.id)
    advert.sell = True
    index = str(uuid.uuid1())
    advert_dict[index] = advert
    bot.send_message(advert.author_chat_id, "send the photo of the item (in one message)",
                     reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(content_types=['document'])
def reject_document(message):
    bot.send_message(message.from_user.id, "Send as photo (not as file)")


@bot.message_handler(content_types=['photo'])
def get_photo(message):
    advert_found = False
    lock.acquire()
    for key, value in advert_dict.items():
        if (value.author_chat_id == message.from_user.id) and (value.ready is False):
            advert_dict[key].photo.append(InputMediaPhoto(message.photo[0].file_id))
            if message.caption:
                advert_dict[key].description = message.caption
            lock.release()
            advert_found = True
            if (message.media_group_id is None) or (len(advert_dict[key].photo) == 1):
                add_caption(key)
            break
    if advert_found is False:
        ask_to_start(message)
        lock.release()


def ask_to_start(message):
    global unfound_media_group_id
    if (len(unfound_media_group_id) == 0) or (message.media_group_id is None) or \
            (message.media_group_id not in unfound_media_group_id):
        unfound_media_group_id.append(message.media_group_id)
        bot.send_message(message.chat.id, "Start with sending /add")


def add_caption(index):
    bot.send_message(advert_dict[index].author_chat_id,
                     "Wait for 5 seconds, to make sure all the photos are delivered")
    time.sleep(5)
    if advert_dict[index].description:
        compose_advert(index)
    else:
        msg = bot.send_message(advert_dict[index].author_chat_id,
                               "Add a description of the item. Your contact will be added automatically.")
        bot.register_next_step_handler(msg, get_description, index)


def get_description(message, index):
    if message.photo:
        get_photo(message)
    elif message.document:
        reject_document(message)
    else:
        advert_dict[index].description = message.text
        compose_advert(index)


def compose_advert(index):
    if advert_dict[index].sell:
        advert_dict[index].description = '#sell' + "\n" + advert_dict[index].description +\
                                         "\n" + advert_dict[index].contact
    else:
        advert_dict[index].description = '#buy' + "\n" + advert_dict[index].description + \
                                         "\n" + advert_dict[index].contact
    if len(advert_dict[index].photo) > 0:
        advert_dict[index].photo[0].caption = advert_dict[index].description
    advert_dict[index].ready = True
    send_or_edit(index)


def send_or_edit(index):
    send_keyboard = types.InlineKeyboardMarkup(row_width=1)
    send_button = types.InlineKeyboardButton(text='Send for review', callback_data='send' + index)
    restart_button = types.InlineKeyboardButton(text='Start over', callback_data='restart' + index)
    edit_button = types.InlineKeyboardButton(text='Edit description', callback_data='edit' + index)
    remove_button = types.InlineKeyboardButton(text='Delete and cancel', callback_data='remove' + index)
    send_keyboard.add(send_button, edit_button, restart_button, remove_button)
    if len(advert_dict[index].photo) > 0:
        bot.send_media_group(advert_dict[index].author_chat_id, advert_dict[index].photo)
    else:
        bot.send_message(advert_dict[index].author_chat_id, advert_dict[index].description)
    save_advert()
    bot.send_message(advert_dict[index].author_chat_id, "Send advertisement, or edit?",
                     reply_markup=send_keyboard)


def moderator(index):
    moderator_keyboard = types.InlineKeyboardMarkup()
    approve_button = types.InlineKeyboardButton(text='Approve', callback_data='approve' + index)
    reject_button = types.InlineKeyboardButton(text='Reject', callback_data='reject' + index)
    moderator_keyboard.add(approve_button, reject_button)
    if len(advert_dict[index].photo) > 0:
        bot.send_media_group(config.moderator_chat_id, advert_dict[index].photo)
    else:
        bot.send_message(config.moderator_chat_id, advert_dict[index].description)
    save_advert()
    bot.send_message(config.moderator_chat_id, "Approve or reject the advertisement?",
                     reply_markup=moderator_keyboard)


@bot.callback_query_handler(func=lambda call: True)
def moderate(call):
    load_advert()
    if call.data.startswith("approve"):
        index = call.data[7:]
        bot.edit_message_text(chat_id=config.moderator_chat_id, message_id=call.message.message_id,
                              text='Advertisement approved')
        if len(advert_dict[index].photo) > 0:
            bot.send_media_group(config.channel_id, advert_dict[index].photo)
        else:
            bot.send_message(config.channel_id, advert_dict[index].description)
        bot.send_message(advert_dict[index].author_chat_id, "Your advertisement was published")
        del advert_dict[index]

    if call.data.startswith("reject"):
        index = call.data[6:]
        bot.edit_message_text(chat_id=config.moderator_chat_id, message_id=call.message.message_id,
                              text='Advertisement rejected')
        bot.send_message(advert_dict[index].author_chat_id, "Your advertisement was rejected")
        del advert_dict[index]

    if call.data.startswith("send"):
        index = call.data[4:]
        bot.edit_message_text(chat_id=advert_dict[index].author_chat_id, message_id=call.message.message_id,
                              text='Advertisement sent to review')
        moderator(index)

    if call.data.startswith("restart"):
        index = call.data[7:]
        bot.edit_message_text(chat_id=advert_dict[index].author_chat_id, message_id=call.message.message_id,
                              text='Starting over')
        del advert_dict[index]
        select_advert_type(call.message)

    if call.data.startswith("edit"):
        index = call.data[4:]
        bot.delete_message(chat_id=advert_dict[index].author_chat_id, message_id=call.message.message_id)
        msg = bot.send_message(advert_dict[index].author_chat_id,
                               "Add a description of the item. Your contact will be added automatically.")
        bot.register_next_step_handler(msg, get_description, index)

    if call.data.startswith("remove"):
        index = call.data[6:]
        bot.edit_message_text(chat_id=advert_dict[index].author_chat_id, message_id=call.message.message_id,
                              text='Advertisement removed')
        del advert_dict[index]

    if call.data.startswith("clear"):
        bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.message_id,
                              text='All unpublished advertisements from you have been cleared')
        bot.send_message(chat_id=call.from_user.id, text='Start with sending /add')
        clear(call)

    if call.data.startswith("cancel"):
        bot.edit_message_text(chat_id=call.from_user.id, message_id=call.message.message_id,
                              text='Start with sending /add')
    save_advert()


bot.polling()
