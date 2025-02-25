import re
import os
from logging import getLogger, ERROR
from os import remove as osremove, walk, path as ospath, rename as osrename
from time import time, sleep
from pyrogram.errors import FloodWait, RPCError
from PIL import Image
from threading import RLock
from bot import user_data, GLOBAL_EXTENSION_FILTER, \
                app, tgBotMaxFileSize, premium_session, config_dict
from bot.helper.ext_utils.fs_utils import take_ss, get_media_info, get_media_streams, get_path_size, clean_unwanted
from bot.helper.ext_utils.bot_utils import get_readable_file_size
from pyrogram.types import Message

LOGGER = getLogger(__name__)
getLogger("pyrogram").setLevel(ERROR)
IMAGE_SUFFIXES = ("JPG", "JPX", "PNG", "CR2", "TIF", "BMP", "JXR", "PSD", "ICO", "HEIC", "JPEG")
class TgUploader:

    def __init__(self, name=None, path=None, size=0, listener=None):
        self.name = name
        self.uploaded_bytes = 0
        self._last_uploaded = 0
        self.__listener = listener
        self.__path = path
        self.__start_time = time()
        self.__total_files = 0
        self.__is_cancelled = False
        self.__as_doc = config_dict['AS_DOCUMENT']
        self.__thumb = f"Thumbnails/{listener.message.from_user.id}.jpg"
        self.__msgs_dict = {}
        self.__corrupted = 0
        self.__resource_lock = RLock()
        self.__is_corrupted = False
        self.__sent_msg = app.get_messages(self.__listener.message.chat.id, self.__listener.uid)
        self.__size = size
        self.__user_settings()
        self.__leech_log = user_data.get('is_leech_log')
        self.__app = app
        self.__user_id = listener.message.from_user.id
        self.isPrivate = listener.message.chat.type in ['private', 'group']

    def upload(self, o_files):
        for dirpath, subdir, files in sorted(walk(self.__path)):
            for file_ in sorted(files):
                if file_ in o_files:
                    continue
                if not file_.lower().endswith(tuple(GLOBAL_EXTENSION_FILTER)):
                    up_path = ospath.join(dirpath, file_)
                    self.__total_files += 1
                    try:
                        if ospath.getsize(up_path) == 0:
                            LOGGER.error(f"{up_path} size is zero, telegram don't upload zero size files")
                            self.__corrupted += 1
                            continue
                    except Exception as e:
                        if self.__is_cancelled:
                            return
                        LOGGER.error(e)
                        continue
                    self.__upload_file(up_path, file_, dirpath)
                    if self.__is_cancelled:
                        return
                    if not self.__listener.isPrivate and not self.__is_corrupted:
                        self.__msgs_dict[self.__sent_msg.link] = file_
                    self._last_uploaded = 0
                    sleep(1)
        if self.__listener.seed and not self.__listener.newDir:
            clean_unwanted(self.__path)
        if self.__total_files <= self.__corrupted:
            self.__listener.onUploadError('Files Corrupted. Check logs!')
            return
        LOGGER.info(f"Leech Completed: {self.name}")
        size = get_readable_file_size(self.__size)
        self.__listener.onUploadComplete(None, size, self.__msgs_dict, self.__total_files, self.__corrupted, self.name)

    def __upload_file(self, up_path, file_, dirpath):
        fsize = ospath.getsize(up_path)
        user_id_ = self.__listener.message.from_user.id

        client = premium_session if fsize > 2097152000 else app
        PREFIX = user_data[user_id_].get('prefix') if user_id_ in user_data and user_data[user_id_].get('prefix') else ''
        CAPTION = user_data[user_id_].get('caption') if user_id_ in user_data and user_data[user_id_].get('caption') else ''
        REMNAME = user_data[user_id_].get('remname') if user_id_ in user_data and user_data[user_id_].get('remname') else ''
        SUFFIX = user_data[user_id_].get('suffix') if user_id_ in user_data and user_data[user_id_].get('suffix') else ''
        FSTYLE = user_data[user_id_].get('cfont')[1] if user_id_ in user_data and user_data[user_id_].get('cfont') else ''

        #MysteryStyle
        if file_.startswith('www'):
            file_ = ' '.join(file_.split()[1:])
        if REMNAME:
            if not REMNAME.startswith('|'):
                REMNAME = f"|{REMNAME}"
            slit = REMNAME.split("|")
            __newFileName = file_
            for rep in range(1, len(slit)):
                args = slit[rep].split(":")
                if len(args) == 3:
                    __newFileName = __newFileName.replace(args[0], args[1], int(args[2]))
                elif len(args) == 2:
                    __newFileName = __newFileName.replace(args[0], args[1])
                elif len(args) == 1:
                    __newFileName = __newFileName.replace(args[0], '')
            file_ = __newFileName
            LOGGER.info("Remname : "+file_)
        if PREFIX:
            if not file_.startswith(PREFIX):
                file_ = f"{PREFIX}{file_}"
        if SUFFIX:
            sufLen = len(SUFFIX)
            fileDict = file_.split('.')
            _extIn = 1 + len(fileDict[-1])
            _extOutName = '.'.join(fileDict[:-1]).replace('.', ' ').replace('-', ' ')
            _newExtFileName = f"{_extOutName}{SUFFIX}.{fileDict[-1]}"
            if len(_extOutName) > (64 - (sufLen + _extIn)):
                _newExtFileName = (
                    _extOutName[: 64 - (sufLen + _extIn)]
                    + f"{SUFFIX}.{fileDict[-1]}"
                            )
            file_ = _newExtFileName
        if PREFIX or REMNAME or SUFFIX:
            new_path = ospath.join(dirpath, file_)
            osrename(up_path, new_path)
            up_path = new_path
        cfont = config_dict['CAPTION_FONT'] if not FSTYLE else FSTYLE
        if CAPTION:
            slit = CAPTION.split("|")
            cap_mono = slit[0].format(
                filename = file_,
                size = get_readable_file_size(ospath.getsize(up_path))
            )
            if len(slit) > 1:
                for rep in range(1, len(slit)):
                    args = slit[rep].split(":")
                    if len(args) == 3:
                        cap_mono = cap_mono.replace(args[0], args[1], int(args[2]))
                    elif len(args) == 2:
                        cap_mono = cap_mono.replace(args[0], args[1])
                    elif len(args) == 1:
                        cap_mono = cap_mono.replace(args[0], '')
        else:
            cap_mono = file_ if FSTYLE == 'r' else f"<{cfont}>{file_}</{cfont}>"

        dumpid = user_data[user_id_].get('userlog') if user_id_ in user_data and user_data[user_id_].get('userlog') else ''
        LEECH_X = int(dumpid) if len(dumpid) != 0 else user_data.get('is_log_leech', [''])[0]
        notMedia = False
        thumb = self.__thumb
        self.__is_corrupted = False
        try:
            is_video, is_audio = get_media_streams(up_path)
            if not self.__as_doc:
                if is_video:
                    duration = get_media_info(up_path)[0]
                    if thumb is None:
                        thumb = take_ss(up_path, duration)
                        if self.__is_cancelled:
                            if self.__thumb is None and thumb is not None and ospath.lexists(thumb):
                                osremove(thumb)
                            return
                    if thumb is not None:
                        with Image.open(thumb) as img:
                            width, height = img.size
                    else:
                        width = 480
                        height = 320
                    if not file_.upper().endswith(("MKV", "MP4")):
                        file_ = f"{ospath.splitext(file_)[0]}.mp4"
                        new_path = ospath.join(dirpath, file_)
                        osrename(up_path, new_path)
                        up_path = new_path
                    if 'is_leech_log' in user_data and user_data.get('is_leech_log'):
                        for leechchat in self.__leech_log:
                            if ospath.getsize(up_path) > tgBotMaxFileSize: usingclient = premium_session
                            else: usingclient = self.__app
                            self.__sent_msg = usingclient.send_video(chat_id=int(leechchat),video=up_path,
                                                                  caption=cap_mono,
                                                                  duration=duration,
                                                                  width=width,
                                                                  height=height,
                                                                  thumb=thumb,
                                                                  supports_streaming=True,
                                                                  disable_notification=True,
                                                                  progress=self.__upload_progress)
                            if config_dict['BOT_PM']:
                                try:
                                    app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                                except Exception as err:
                                    LOGGER.error(f"Failed To Send Video in PM:\n{err}")
                            if len(dumpid) != 0:
                                try:
                                    app.copy_message(chat_id=LEECH_X, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                                except Exception as err:
                                    LOGGER.error(f"Failed To Send Video in dump:\n{err}")

                    else:
                        self.__sent_msg = self.__sent_msg.reply_video(video=up_path,
                                                                      quote=True,
                                                                      caption=cap_mono,
                                                                      duration=duration,
                                                                      width=width,
                                                                      height=height,
                                                                      thumb=thumb,
                                                                      supports_streaming=True,
                                                                      disable_notification=True,
                                                                      progress=self.__upload_progress)
                        if not self.isPrivate and config_dict['BOT_PM']:
                            try:
                                app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                            except Exception as err:
                                LOGGER.error(f"Failed To Send Vedio in PM:\n{err}")
                elif is_audio:
                    duration , artist, title = get_media_info(up_path)
                    if 'is_leech_log' in user_data and user_data.get('is_leech_log'):
                        for leechchat in self.__leech_log:
                            if ospath.getsize(up_path) > tgBotMaxFileSize: usingclient = premium_session
                            else: usingclient = self.__app
                            self.__sent_msg = usingclient.send_audio(chat_id=int(leechchat),audio=up_path,
                                                                  caption=cap_mono,
                                                                  duration=duration,
                                                                  performer=artist,
                                                                  title=title,
                                                                  thumb=thumb,
                                                                  disable_notification=True,
                                                                  progress=self.__upload_progress)
                            if config_dict['BOT_PM']:
                                try:
                                    app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                                except Exception as err:
                                    LOGGER.error(f"Failed To Send Audio in PM:\n{err}")
                            if len(dumpid) != 0:
                                try:
                                    app.copy_message(chat_id=LEECH_X, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                                except Exception as err:
                                    LOGGER.error(f"Failed To Send Audio in dump:\n{err}")
                    else:
                        self.__sent_msg = self.__sent_msg.reply_audio(audio=up_path,
                                                                      quote=True,
                                                                      caption=cap_mono,
                                                                      duration=duration,
                                                                      performer=artist,
                                                                      title=title,
                                                                      thumb=thumb,
                                                                      disable_notification=True,
                                                                      progress=self.__upload_progress)
                        if not self.isPrivate and config_dict['BOT_PM']:
                            try:
                                app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                            except Exception as err:
                                LOGGER.error(f"Failed To Send Audio in PM:\n{err}")

                elif file_.upper().endswith(IMAGE_SUFFIXES):
                    if 'is_leech_log' in user_data and user_data.get('is_leech_log'):
                        for leechchat in self.__leech_log:
                            if ospath.getsize(up_path) > tgBotMaxFileSize: usingclient = premium_session
                            else: usingclient = self.__app
                            self.__sent_msg = usingclient.send_photo(chat_id=int(leechchat),
                                                                photo=up_path,
                                                                caption=cap_mono,
                                                                disable_notification=True,
                                                                progress=self.__upload_progress)
                            if config_dict['BOT_PM']:
                                try:
                                    app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                                except Exception as err:
                                    LOGGER.error(f"Failed To Send Image in PM:\n{err}")
                            if len(dumpid) != 0:
                                try:
                                    app.copy_message(chat_id=LEECH_X, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                                except Exception as err:
                                    LOGGER.error(f"Failed To Send Image in dump:\n{err}")
                    else:
                        self.__sent_msg = self.__sent_msg.reply_photo(photo=up_path,
                                                                      quote=True,
                                                                      caption=cap_mono,
                                                                      disable_notification=True,
                                                                      progress=self.__upload_progress)
                        if not self.isPrivate and config_dict['BOT_PM']:
                            try:
                                app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                            except Exception as err:
                                LOGGER.error(f"Failed To Send Image in PM:\n{err}")
                else:
                    notMedia = True
            if self.__as_doc or notMedia:
                if is_video and thumb is None:
                    thumb = take_ss(up_path, None)
                    if self.__is_cancelled:
                        if self.__thumb is None and thumb is not None and ospath.lexists(thumb):
                            osremove(thumb)
                        return
                if 'is_leech_log' in user_data and user_data.get('is_leech_log'):
                    for leechchat in self.__leech_log:
                        if ospath.getsize(up_path) > tgBotMaxFileSize: usingclient = premium_session
                        else: usingclient = self.__app
                        self.__sent_msg = usingclient.send_document(chat_id=int(leechchat),
                                                                document=up_path,
                                                                thumb=thumb,
                                                                caption=cap_mono,
                                                                disable_notification=True,
                                                                progress=self.__upload_progress)
                        if len(dumpid) != 0:
                            try:
                                app.copy_message(chat_id=LEECH_X, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                            except Exception as err:
                                LOGGER.error(f"Failed To Send Document in dump:\n{err}")
                        if config_dict['BOT_PM']:
                            try:
                                app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                            except Exception as err:
                                LOGGER.error(f"Failed To Send Document in PM:\n{err}")
                else:
                    self.__sent_msg = self.__sent_msg.reply_document(document=up_path,
                                                                     quote=True,
                                                                     thumb=thumb,
                                                                     caption=cap_mono,
                                                                     disable_notification=True,
                                                                     progress=self.__upload_progress)
                    if not self.isPrivate and config_dict['BOT_PM']:
                            try:
                                app.copy_message(chat_id=self.__user_id, from_chat_id=self.__sent_msg.chat.id, message_id=self.__sent_msg.id)
                            except Exception as err:
                                LOGGER.error(f"Failed To Send Document in PM:\n{err}")
        except FloodWait as f:
            LOGGER.warning(str(f))
            sleep(f.value)
        except RPCError as e:
            LOGGER.error(f"RPCError: {e} Path: {up_path}")
            self.__corrupted += 1
            self.__is_corrupted = True
        except Exception as err:
            LOGGER.error(f"{err} Path: {up_path}")
            self.__corrupted += 1
            self.__is_corrupted = True
        if self.__thumb is None and thumb is not None and ospath.lexists(thumb):
            osremove(thumb)
        if not self.__is_cancelled and \
                   (not self.__listener.seed or self.__listener.newDir or dirpath.endswith("splited_files_mltb")):
            try:
                osremove(up_path)
            except:
                pass

    def __upload_progress(self, current, total):
        if self.__is_cancelled:
            app.stop_transmission()
            return
        with self.__resource_lock:
            chunk_size = current - self._last_uploaded
            self._last_uploaded = current
            self.uploaded_bytes += chunk_size

    def __user_settings(self):
        user_id = self.__listener.message.from_user.id
        user_dict = user_data.get(user_id, False)
        if user_dict:
            self.__as_doc = user_dict.get('as_doc', False)
        if not ospath.lexists(self.__thumb):
            self.__thumb = None

    @property
    def speed(self):
        with self.__resource_lock:
            try:
                return self.uploaded_bytes / (time() - self.__start_time)
            except:
                return 0

    def cancel_download(self):
        self.__is_cancelled = True
        LOGGER.info(f"Cancelling Upload: {self.name}")
        self.__listener.onUploadError('Your upload has been stopped!')
