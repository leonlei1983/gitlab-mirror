import telegram
from configparser import ConfigParser


class Notification:
    _config = None
    _default_session = "telegram"

    def __init__(self, config_path="config.cfg"):
        self._config = ConfigParser()
        self._config.read(config_path)

        self._bot = telegram.Bot(token=self._cfg_get("bot_token"))
        self._chat_ids = self._cfg_get("bot_chat_ids").split(',')

    def _cfg_get(self, option):
        return self._config.get(self._default_session, option)

    def _cfg_get_int(self, option):
        return self._config.getint(self._default_session, option)

    def send_message(self, message):
        if not self._chat_ids:
            return

        for chat_id in self._chat_ids:
            self._bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=self._cfg_get("parse_mode"),
                timeout=self._cfg_get_int("timeout"),
            )


if __name__ == "__main__":
    notify = Notification("config.cfg")
    notify.send_message("`test`")
