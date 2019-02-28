from flask import Flask, request, abort

from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import *

from imgurpython import ImgurClient
from imgurpython.helpers.error import ImgurClientError

import subprocess

import tempfile, shutil, os
from PIL import Image
from io import BytesIO

import json
import sys
import urllib.request
import urllib.error
import time
import datetime
import gspread

from oauth2client.service_account import ServiceAccountCredentials as SAC

from config import client_id, client_secret, album_id, access_token, refresh_token

#from pydarknet import Detector, Image

app = Flask(__name__)

# Channel Access Token
line_bot_api = LineBotApi('')
# Channel Secret
handler = WebhookHandler('')

# Google Sheet Config
GDriveJSON = 'LineBotSheet.json'
GSpreadSheet = 'LineBotSheet'

static_tmp_path = os.path.join(os.path.dirname(__file__), 'static', 'tmp')

# 監聽所有來自 /callback 的 Post Request
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 處理 event
@handler.add(FollowEvent)
def handle_follow(event):
    pass

@handler.add(UnfollowEvent)
def handle_unfollow(event):
    pass

@handler.add(JoinEvent)
def handle_join(event):
    pass

@handler.add(LeaveEvent)
def handle_leave(event):
    pass

# 處理文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    message = TextSendMessage(text="請輸入圖片")
    line_bot_api.reply_message(event.reply_token, message)
    return 0

# 處理圖片訊息
@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    # save image
    try:
        message_content = line_bot_api.get_message_content(event.message.id)
        i = Image.open(BytesIO(message_content.content))
        filename = './images/' + event.message.id + '.jpg'
        i.save(filename)

        message = TextSendMessage(text="上傳成功，開始辨識")
        line_bot_api.reply_message(event.reply_token, message)
    
    except:
        message = TextSendMessage(text="系統錯誤，請重新上傳一次")
        line_bot_api.reply_message(event.reply_token, message)

        return 0

    # yolo detector
    try:
        command = ("darknet.exe detect cfg/yolov3-tiny.cfg yolov3-tiny.weights {0}".format(filename))
        subprocess.call(command, shell=True)

    except:
        message = TextSendMessage(text="系統錯誤，無法辨識")
        line_bot_api.reply_message(event.reply_token, message)        

    # upload to imgur
    try:
        client = ImgurClient(client_id, client_secret, access_token, refresh_token)
        config = {
            'album': album_id,
            'name': event.message.id,
            'title': event.message.id,
            'description': 'yolo'
        }
        client.upload_from_path('./predictions.jpg', config=config, anon=False)

        # reply url to user
        images = client.get_album_images(album_id)
        url = images[-1].link
        image_message = ImageSendMessage(
            original_content_url=url,
            preview_image_url=url
        )

        line_bot_api.push_message(event.source.user_id, image_message)

    except:
       message = TextSendMessage(text="辨識完成，但上傳至imgur失敗")
       line_bot_api.reply_message(event.reply_token, message)
       return 0    

    # 連線至Google Sheet
    try:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive',
                 'https://www.googleapis.com/auth/drive.readonly',
                 'https://www.googleapis.com/auth/drive.file',
                 'https://www.googleapis.com/auth/spreadsheets',
                 'https://www.googleapis.com/auth/spreadsheets.readonly']
        key = SAC.from_json_keyfile_name(GDriveJSON, scope)
        gc = gspread.authorize(key)
        worksheet = gc.open(GSpreadSheet).sheet1 # sheet1: member

    except Exception as ex:
        print('無法連線Google Sheet', ex)
        message = TextSendMessage(text="無法連線到Google Sheet")
        line_bot_api.reply_message(event.reply_token, message)
        sys.exit(1)
        return 0

    # 讀取紀錄文件
    class_set = set([])
    data = 'class.txt'
    with open('%s' %data, 'r') as d:
        while True:
            lines = d.readlines(10000)
            for line in lines:
                temp = line[:-1] # remove '\n'
                class_set.add(temp)
            if not lines: break

    class_message = ""
    i = 0
    for item in class_set:
        class_message += '%s' %item
        if not(i==len(class_set)-1):
            class_message += ', '
        i += 1

    # 使用Google Sheet紀錄發現物種
    try:
        date = json.dumps(datetime.datetime.now(), cls=Encoder, indent=4)
        worksheet.append_row((date, class_message))
        spreadsheet_id = ''

        return 0

    except Exception as ex:    
        print('無法使用Google Sheet', ex)
        message = TextSendMessage(text="無法使用Google Sheet")
        line_bot_api.reply_message(event.reply_token, message)
        sys.exit(1)
        return 0    


class Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        else:
            return json.JSONEncoder.default(self, obj)

def get_google_sheet(spreadsheet_id, range_name):
    """ Retrieve sheet data using OAuth credentials and Google Python API. """
    gsheet = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    return gsheet


import os
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
