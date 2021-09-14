import yaml
import os
import re


class Config:
    __config = {}
    __flatten_config = {}
    __root_dir = None
    __config_dir = None
    __v_channel_dir = None

    def __init__(self) -> None:
        self.__root_dir = os.path.abspath(os.getcwd())
        self.__config_dir = os.path.join(self.__root_dir, 'Config')
        self.__v_channel_dir = os.path.join(self.__config_dir, 'VirtualChannels')

        # TODO add multi-dic merging - this will allow use the first one config as default values
        self.__read_config_file(os.path.join(self.__config_dir, 'main.example.yaml'))
        self.__read_config_file(os.path.join(self.__config_dir, 'main.yaml'))
        self.read_v_channel_configs()

        self.__flat_config(self.__config)

    def get_root_dir(self, path='') -> str:
        return os.path.abspath(os.path.join(self.__root_dir, path))

    def get_config_dir(self, path='') -> str:
        return os.path.abspath(os.path.join(self.__root_dir, path))

    def read_v_channel_configs(self) -> None:
        # TODO stubbing virtual channels config reading

        self.__config['v-channels'] = {
            'stub': {'minDelay': 1, 'maxDelay': 6},
            'mock': {'minDelay': 2, 'maxDelay': 3},
            'test': {'minDelay': 1, 'maxDelay': 3},
            'telegram': {**self.__config['dog-nail']}
        }

    def get(self, path, default=None):
        path = str(path)

        if path in self.__flatten_config:
            return self.__flatten_config[path]
        elif '*' in path:
            params = {}

            path = re.compile(path.replace('*', '[\\w\\-]+').replace('.', '\\.'), re.I | re.U)

            for key in self.__flatten_config.keys():
                if path.fullmatch(key):
                    params[key] = self.__flatten_config[key]

            return params
        else:
            return default

    def get_raw(self) -> dict:
        return self.__config

    def __flat_config(self, config, *, parent_key='', separator='.') -> None:
        for key in config:
            value = config[key]
            current_key = parent_key + key

            if isinstance(value, dict) or isinstance(value, list) or isinstance(value, tuple):
                self.__flat_config(value, parent_key=current_key + separator)
            else:
                self.__flatten_config[current_key] = value

    def __read_config_file(self, path) -> None:
        path = os.path.abspath(path)

        if os.path.isfile(path) and not os.path.islink(path):
            with open(path, 'r') as file:
                self.__config.update(yaml.safe_load(file))

                file.close()
