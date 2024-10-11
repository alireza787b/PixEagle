# src/classes/parameters.py

import os
import configparser
import json
import ast

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Automatically loads all configuration parameters from the config.ini file.
    Configurations are set as class variables, maintaining compatibility with existing code.
    """

    @classmethod
    def load_config(cls, config_file='configs/config.ini'):
        """
        Class method to load configurations from the config.ini file and set class variables.
        """
        config = configparser.ConfigParser()
        config.read(config_file)

        for section in config.sections():
            for key, value in config.items(section):
                # Construct the attribute name in uppercase to match existing usage
                attr_name = key.upper()

                # Parse the value to the appropriate data type
                parsed_value = cls.parse_value(value)

                # Set the attribute as a class variable
                setattr(cls, attr_name, parsed_value)

    @staticmethod
    def parse_value(value):
        """
        Attempts to parse a configuration value into an appropriate data type.
        The order of parsing attempts is:
        1. Boolean
        2. Integer
        3. Float
        4. JSON (dict, list)
        5. Tuple
        6. String (default)
        """
        # Strip quotes if present
        value = value.strip('\'"')

        # Try boolean
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'

        # Try integer
        try:
            return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Try JSON
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass

        # Try Python literal (tuple, list, dict, etc.)
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass

        # Default to string
        return value

# Load the configurations upon module import
Parameters.load_config()
