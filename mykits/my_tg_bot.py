#!/usr/bin/env python3
# encoding=utf8
import argparse
import os
import re
import shlex
import subprocess
import time
from pprint import pformat

from telegram.ext import MessageHandler, Filters, CallbackContext

from mylib.log import get_logger
from mylib.os_util import read_json_file, monitor_sub_process_tty_frozen, ProcessTTYFrozen
from mylib.text import decode
from mylib.tg_bot import SimpleBot, meta_deco_handler_method, CommandHandler, Update
from mylib.tricks import ArgParseCompactHelpFormatter, meta_deco_retry, module_sqlitedict_with_dill

sqlitedict = module_sqlitedict_with_dill()
mt = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(os.path.realpath(__file__))))


@meta_deco_retry(retry_exceptions=ProcessTTYFrozen, max_retries=-1)
def bldl_retry_frozen(*args: str):
    p = subprocess.Popen(['bldl.sh.cmd', *args], stdout=subprocess.PIPE)
    return monitor_sub_process_tty_frozen(p, encoding='u8')


@meta_deco_retry(retry_exceptions=ProcessTTYFrozen, max_retries=-1)
def ytdl_retry_frozen(*args: str):
    p = subprocess.Popen(['ytdl.sh.cmd', *args], stdout=subprocess.PIPE)
    return monitor_sub_process_tty_frozen(p, encoding='u8', timeout=60)


def line2args(line: str):
    args = shlex.split(line.strip())
    if args[0] in '+-*!':
        args.pop(0)
    return args


class MyAssistantBot(SimpleBot):
    def __init__(self, config_file: str, **kwargs):
        config = read_json_file(config_file)
        data_file = os.path.splitext(config_file)[0] + '.db'
        with sqlitedict.SqliteDict(data_file) as sd:
            data = dict(sd)
        super().__init__(token=config['token'], whitelist=config.get('user_whitelist'), data=data, **kwargs)
        self._data_file = data_file

    @meta_deco_handler_method(MessageHandler, filters=Filters.regex(
        re.compile(r'BV[\da-zA-Z]{10}|av\d+')))
    def _bldl(self, update, *args):
        try:
            self.__data_save__()
        except TypeError as e:
            self.__reply_md_code_block__(f'{str(e)}\n{repr(e)}', update)
        args_l = [line2args(line) for line in update.message.text.splitlines()]
        for args in args_l:
            args_s = ' '.join([shlex.quote(a) for a in args])
            try:
                self.__reply_md_code_block__(f'+ {args_s}', update)
                p, out, err = bldl_retry_frozen(*args)
                if p.returncode:
                    echo = ''.join([decode(b).rsplit('\r', maxsplit=1)[-1] for b in out.readlines()[-5:]])
                    self.__requeue_failed_update__(update)
                    self.__reply_md_code_block__(f'- {args_s}\n{echo}', update)
                else:
                    echo = ''.join([s for s in [decode(b) for b in out.readlines()] if '─┤' not in s])
                    self.__reply_md_code_block__(f'* {args_s}\n{echo}', update)
            except Exception as e:
                self.__reply_md_code_block__(f'! {args_s}\n{str(e)}\n{repr(e)}', update)
                self.__requeue_failed_update__(update)

    @meta_deco_handler_method(MessageHandler, filters=Filters.regex(
        re.compile(r'youtube|youtu\.be|iwara|pornhub')))
    def _ytdl(self, update: Update, *args):
        try:
            self.__data_save__()
        except TypeError as e:
            self.__reply_md_code_block__(f'{str(e)}\n{repr(e)}', update)
        args_l = [line2args(line) for line in update.message.text.splitlines()]
        for args in args_l:
            args_s = ' '.join([shlex.quote(a) for a in args])
            try:
                self.__reply_md_code_block__(f'+ {args_s}', update)
                p, out, err = ytdl_retry_frozen(*args)
                echo = ''.join([re.sub(r'.*\[download]', '[download]', decode(b).rsplit('\r', maxsplit=1)[-1]) for b in
                                out.readlines()[-10:]])
                if p.returncode:
                    self.__requeue_failed_update__(update)
                    self.__reply_md_code_block__(f'- {args_s}\n{echo}', update)
                else:
                    self.__reply_md_code_block__(f'* {args_s}\n{echo}', update)
            except Exception as e:
                self.__reply_md_code_block__(f'! {args_s}\n{str(e)}\n{repr(e)}', update)
                self.__requeue_failed_update__(update)

    @meta_deco_handler_method(CommandHandler)
    def _secret(self, update: Update, *args):
        self.__typing__(update)
        for name in ('effective_message', 'effective_user'):
            self.__reply_md_code_block__(f'{name}\n{pformat(getattr(update, name).to_dict())}', update)
        self.__reply_md_code_block__(f'bot.get_me()\n{pformat(self.__bot__.get_me().to_dict())}', update)

    @meta_deco_handler_method(CommandHandler, on_menu=True, pass_args=True)
    def sleep(self, u: Update, c: CallbackContext):
        """sleep some time (unit: sec)"""
        args = c.args or [0]
        t = float(args[0])
        self.__reply_text__(f'sleep {t} seconds', u)
        time.sleep(t)
        self.__reply_text__('awoken!', u)

    def __data_save__(self):
        super().__data_save__()
        print(f'{self.__updater__.dispatcher.update_queue.qsize()} updates in queue')
        self.__data__['update_queue'] = self.__updater__.dispatcher.update_queue
        with sqlitedict.SqliteDict(self._data_file, autocommit=True) as sd:
            sd.update(self.__data__, mtime=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
        with sqlitedict.SqliteDict(self._data_file) as sd:
            print(f"{sd['update_queue'].qsize()} updates saved")


def main():
    ap = argparse.ArgumentParser(formatter_class=ArgParseCompactHelpFormatter)
    ap.add_argument('-c', '--config-file', metavar='path', required=True)
    ap.add_argument('-v', '--verbose', action='store_true')
    ap.add_argument('-T', '--timeout', type=float)
    parsed_args = ap.parse_args()
    config_file = parsed_args.config_file
    timeout = parsed_args.timeout

    if parsed_args.verbose:
        log_lvl = 'DEBUG'
        print(parsed_args)
    else:
        log_lvl = 'INFO'
    get_logger('telegram').setLevel(log_lvl)
    bot = MyAssistantBot(config_file, timeout=timeout, auto_run=False)
    bot.__run__()


if __name__ == '__main__':
    # ensure_sigint_signal()
    main()
