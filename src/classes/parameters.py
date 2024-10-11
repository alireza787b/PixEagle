# src/classes/parameters.py

import yaml
import os

class Parameters:
    """
    Central configuration class for the PixEagle project.
    Automatically loads all configuration parameters from the config.yaml file.
    Configurations are set as class variables, maintaining compatibility with existing code.
    """

    @classmethod
    def load_config(cls, config_file='configs/config.yaml'):
        """
        Class method to load configurations from the config.yaml file and set class variables.
        """
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        # Iterate over all top-level keys (sections)
        for section, params in config.items():
            for key, value in params.items():
                # Construct the attribute name in uppercase to match existing usage
                attr_name = key.upper()
                # Set the attribute as a class variable
                setattr(cls, attr_name, value)

    @classmethod
    def get_section(cls, section_name):
        """
        Optional method to get all parameters in a section.
        """
        # This method can be used to retrieve a dictionary of parameters for a specific section
        pass  # Implement if needed

# Load the configurations upon module import
Parameters.load_config()
